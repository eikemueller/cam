#!/usr/bin/python3

import io
import logging
import socketserver
from http import server
from threading import Condition
import time
from typing import Optional
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import os
import logging
from pathlib import Path

import cv2
from picamera2 import MappedArray, Picamera2
from picamera2.encoders import MJPEGEncoder, H264Encoder
from picamera2.outputs import FileOutput, Output

# PAGE = """\
# <html>
# <head>
# <title>picamera2 MJPEG streaming demo</title>
# </head>
# <body>
# <h1>Picamera2 MJPEG Streaming Demo</h1>
# <img src="stream.mjpg" width="640" height="480" />
# </body>
# </html>
# """

logging.basicConfig(format='[%(levelname)s] %(asctime)s %(message)s', level=logging.INFO)
logger = logging.getLogger()

class Clock():
    def __init__(self):
        self.offset: int = 0
    
    def getTimestamp(self) -> int:
        return time.clock_gettime_ns(time.CLOCK_BOOTTIME) + self.offset
    
    def getTimeString(self) -> str:
        ts = self.getTimestamp()
        return datetime.fromtimestamp(ts/1000000000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    def setTime(self, timestamp: int):
        self.offset = timestamp - time.clock_gettime_ns(time.CLOCK_BOOTTIME)

CLOCK = Clock()

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame: Optional[bytes] = None
        self.condition = Condition()

    def write(self, buf: Optional[bytes]):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

DAY_DURATION = 24*60*60*1000000000
RECORD_DURATION = 60*60*1000000000

class TimeRange():
    def __init__(self, begin: int, end: int):
        self._begin = begin
        self._end = end

    def start(self, timestamp: int) -> Optional[int]:
        timeonly = timestamp % DAY_DURATION
        day = timestamp - timeonly
        if (timeonly < self._begin):
            return None
        if (timeonly >= self._end):
            return None
        start = timeonly - (timeonly % RECORD_DURATION)
        if (start < self._begin):
            start = self._begin
        return start + day
    def to_str(self) -> str:
        begin = datetime.fromtimestamp(self._begin/1000000000, tz=timezone.utc).strftime("%H:%M")
        if self._end == DAY_DURATION:
            end = "24:00"
        else:
            end = datetime.fromtimestamp(self._end/1000000000, tz=timezone.utc).strftime("%H:%M")
        return begin + "-" + end

class ParseException(Exception):
    pass

class Schedule():
    def __init__(self):
        self._ranges: list[TimeRange] = []
        self._name: str = ""
        self._condition = Condition()

    def set_schedule(self, ranges_str: str, name: str) -> Optional[str]:
        try:
            ranges: list[TimeRange] = self._parse_timeranges(ranges_str)
        except Exception as error:
            return str(error)
        
        logger.info(ranges)

        with self._condition:
            self._ranges = ranges
            self._name = name
        return None

    def get_schedule(self) -> Optional[tuple[str, str]]:
        with self._condition:
            if not self._ranges:
                return None
            ranges_str = []
            for range in self._ranges:
                ranges_str.append(range.to_str())
            return (", ".join(ranges_str), self._name)
        
    def stop_recording(self):
        with self._condition:
            self._ranges = []
            self._name = ""

    def should_record(self, timestamp: int) -> Optional[str]:
        with self._condition:
            current_ranges = self._ranges
            current_name = self._name
        for range in current_ranges:
            start = range.start(timestamp)
            if (start is not None):
                #return start
                return current_name + '-' + datetime.fromtimestamp(start/1000000000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        return None
    
    def _parse_timeranges(self, data: str) -> list[TimeRange]:
        parts = data.split(",")
        time_ranges: list[TimeRange] = []
        for part in parts:
            time_ranges.append(self._parse_timerange(part))
        return time_ranges
    
    def _parse_timerange(self, data: str) -> TimeRange:
        parts = data.strip().split("-", 1)
        if len(parts) != 2:
            raise ParseException("timerange needs begin and end, got {}".format(data))
        try:
            begin = self._parse_time(parts[0])
        except ParseException as error:
            # error.add_note("Could not parse begin of timerange {}".format(data))
            raise ParseException("Faild to parse begin of timerange {}, got {}".format(data, error.message))
        try: 
            end = self._parse_time(parts[1])
        except ParseException as error:
            # error.add_note("Could not parse end of timerange {}".format(data))
            raise ParseException("Faild to parse end of timerange {}, got {}".format(data, error.message))
        return TimeRange(begin, end)
    
    def _parse_time(self, data: str) -> int:
        parts = data.strip().split(':', 1)
        try:
            hour = int(parts[0])
        except ValueError:
            raise ParseException("could not parse {}, as hour".format(parts[0]))
        minute = 0
        if len(parts) > 1:
            try:
                minute = int(parts[1])
            except ValueError:
                raise ParseException("could not parse {}, as minute".format(parts[1]))

        if hour < 0 or hour > 24:
            raise ParseException("hour needs to be beween 0 and 24, got {:02d}".format(hour))
        if minute < 0 or minute > 60:
            raise ParseException("minute needs to be beween 0 and 60, got {:02d}".format(minute))
        if hour == 24 and minute > 0:
            raise ParseException("for hour 24 minutes need to be 0, got {:02d}:{:02d}".format(hour, minute))

        return (hour*60+minute)*60*1000000000
        
    
SCHEDULE = Schedule()

class RecordOutput(FileOutput):
    def __init__(self, record_name: str):
        logger.info("New record")
        self.record_name = record_name
        self._h264file = "tmp/" + record_name + ".h264"
        self._timestampfile = "tmp/" + record_name + "-timestamp.txt"
        self._outputfile = "recordings/" + record_name + ".mkv"
        self._firstframe = True
        self._timestamp_offset = 0
        super().__init__(file = self._h264file, pts = self._timestampfile)

    def outputframe(self, frame: bytes, keyframe: Optional[bool] = True, timestamp: Optional[int] = None):
        if self._firstframe:
            self._firstframe = False
            print("# timestamp format v2", file=self.ptsoutput, flush=True)
            if timestamp is not None:
                self._timestamp_offset = timestamp
                print("timeframe offset " + str(timestamp))
        adjusted_timestamp = timestamp
        if adjusted_timestamp is not None:
            adjusted_timestamp = adjusted_timestamp - self._timestamp_offset
        super().outputframe(frame, keyframe, adjusted_timestamp)

    def stop(self):
        super().stop()
        logger.info("start mkvmerge")
        subprocess.Popen(["mkvmerge", "-o", self._outputfile, "--timestamps", "0:"+self._timestampfile, self._h264file])
        logger.info("end mkvmerge")

class RecorderOutput(Output):
    def __init__(self):
        self._record: Optional[RecordOutput] = None

    def outputframe(self, frame: bytes, keyframe: Optional[bool] = True, timestamp: Optional[int] = None):
        output_to_use = self._getOutput(keyframe)
        if output_to_use is None:
            return
        output_to_use.outputframe(frame, keyframe, timestamp)
    
    def stop(self):
        self._finish()

    def _getOutput(self, keyframe: Optional[bool]) -> Optional[RecordOutput]:
        if keyframe == False: # What does keyframe = None mean?  
            return self._record
        clock = CLOCK.getTimestamp()
        record_name = SCHEDULE.should_record(clock)
        if record_name is None:
            self._finish()
            return None
        current_record = self._record
        if current_record is None:
            self._new_record(record_name)
        elif current_record.record_name != record_name:
            self._finish()
            self._new_record(record_name)
        
        return self._record

    def _finish(self):
        if self._record is not None:
            self._record.stop()
        self._record = None

    def _new_record(self, record_name: str):
        self._record = RecordOutput(record_name)
        self._record.start()

class StreamingHandler(server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        logger.info("Get " + path)
        # if self.path == '/':
        #     self.send_response(301)
        #     self.send_header('Location', '/index.html')
        #     self.end_headers()
        # elif self.path == '/index.html':
        #     content = PAGE.encode('utf-8')
        #     self.send_response(200)
        #     self.send_header('Content-Type', 'text/html')
        #     self.send_header('Content-Length', len(content))
        #     self.end_headers()
        #     self.wfile.write(content)
        if path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with streaming_output.condition:
                        streaming_output.condition.wait()
                        frame = streaming_output.frame
                    if frame is None:
                        continue
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        elif path == '/status':
            self._send_status()
        elif path == '/start_recording':
            params = parse_qs(urlparse(self.path).query)
            logger.info(params)
            if "timestamp" in params:
                try:
                    now = int(params["timestamp"][0])
                    CLOCK.setTime(now*1000000)
                except:
                    logger.info("failed to parse timestamp")
                    self._send_status()
                    return
            else:
                self._send_status()
                return
            if "name" in params:
                name = params["name"][0]
            else:
                self._send_status()
                return
            if "schedule" in params:
                schedule = params["schedule"][0]
            else:
                self._send_status()
                return
            error = SCHEDULE.set_schedule(ranges_str=schedule, name=name)
            if error is not None:
                logger.info(error)
            self._send_status()
        elif path == '/stop_recording':
            logger.info("stop recording")
            SCHEDULE.stop_recording()
            logger.info("recording stopped")
            self._send_status() 
        else:
            super().do_GET()

    def _send_status(self):
        current_schedule = SCHEDULE.get_schedule()
        if (current_schedule is not None):
            content = "<h1>Currently recording</h1>Name: {name}<br>Schedule: {schedule}<br><button hx-get=\"/stop_recording\" hx-target=\"#status\">Stop Recording</button>".format(name = current_schedule[1], schedule = current_schedule[0]).encode('utf-8')
        else:
            content = "<h1>Start new Recording</h1><form hx-get=\"/start_recording\" hx-target=\"#status\" hx-vars=\"timestamp:currentTimestamp()\"><div><label>Recording Name:</label><input type=\"text\" name=\"name\" value=\"\"></div><div><label>Recording Schedule:</label><input type=\"text\" name=\"schedule\" value=\"\"></div><button>Start Recording</botton></form>".encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', len(content))
        self.end_headers()
        self.wfile.write(content)


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

os.chdir(Path(__file__).parent)
picam2 = Picamera2()
# video_config = picam2.create_video_configuration(main={"size": (1920, 1080)},
#                                                  lores={"size": (640, 480)})
# video_config = picam2.create_video_configuration(main={"size": (640, 480)},
#                                                  lores={"size": (640, 480)})
# video_config = picam2.create_video_configuration(main={"size": (1920, 1080)})
video_config = picam2.create_video_configuration()
picam2.configure(video_config)

colour = (0, 255, 0)
origin = (0, 30)
font = cv2.FONT_HERSHEY_SIMPLEX
scale = 1
thickness = 2

def apply_timestamp(request):
    timestamp = CLOCK.getTimeString()
    with MappedArray(request, "main") as m:
        cv2.putText(m.array, timestamp, origin, font, scale, colour, thickness)


picam2.pre_callback = apply_timestamp
streaming_output = StreamingOutput()
picam2.start_recording(MJPEGEncoder(), FileOutput(streaming_output))
#picam2.start_recording(MJPEGEncoder(), FileOutput(streaming_output), name="lores")
picam2.start_recording(H264Encoder(), RecorderOutput())

logger.info("start server")
logger.info(os.getcwd())
try:
    address = ('', 8000)
    server = StreamingServer(address, StreamingHandler)
    server.serve_forever()
finally:
    logger.info("done")
    picam2.stop_recording()