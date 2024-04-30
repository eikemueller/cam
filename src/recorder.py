from typing import Optional
import subprocess
import logging
from schedule import Schedule
import logging

from picamera2.outputs import FileOutput, Output

logging.basicConfig(format='[%(levelname)s] %(asctime)s %(message)s', level=logging.INFO)
logger = logging.getLogger()

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
    def __init__(self, schedule: Schedule):
        self._schedule: Schedule = schedule
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
        record_name = self._schedule.should_record()
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