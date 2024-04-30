import logging
import socketserver
from http import server
from urllib.parse import urlparse, parse_qs
from cameracontrol import CameraControl

logging.basicConfig(format='[%(levelname)s] %(asctime)s %(message)s', level=logging.INFO)
logger = logging.getLogger()

def streaming_handler(camera_control: CameraControl):
    class StreamingHandler(server.SimpleHTTPRequestHandler):
        _camera_control = camera_control

        def do_GET(self):
            path = urlparse(self.path).path
            logger.info("Get " + path)
            if path == '/stream.mjpg':
                self.send_response(200)
                self.send_header('Age', 0)
                self.send_header('Cache-Control', 'no-cache, private')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
                self.end_headers()
                self._camera_control.new_stream()
                try:
                    while True:
                        with self._camera_control.streaming_output.condition:
                            self._camera_control.streaming_output.condition.wait()
                            frame = self._camera_control.streaming_output.frame
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
                    self._camera_control.end_stream()
            elif path == '/status':
                self._send_status()
            elif path == '/start_recording':
                params = parse_qs(urlparse(self.path).query)
                logger.info(params)
                if "timestamp" in params:
                    try:
                        now = int(params["timestamp"][0])
                        self._camera_control.set_time(now)
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
                error = self._camera_control.record(name = name, schedule = schedule)
                if error is not None:
                    logger.info(error)
                self._send_status()
            elif path == '/stop_recording':
                logger.info("stop recording")
                self._camera_control.stop_recording()
                logger.info("recording stopped")
                self._send_status()
            elif path == '/set_time':
                params = parse_qs(urlparse(self.path).query)
                logger.info(params)
                if "timestamp" in params:
                    try:
                        now = int(params["timestamp"][0])
                        self._camera_control.set_time(now)
                    except:
                        logger.info("failed to parse timestamp")
                        self._send_status()
                        return
                self._send_status()
            else:
                super().do_GET()

        def _send_status(self):
            current_schedule = self._camera_control.get_schedule()
            if (current_schedule is not None):
                content = "<h1>Currently recording</h1>Name: {name}<br>Schedule: {schedule}<br><button hx-get=\"/stop_recording\" hx-target=\"#status\">Stop Recording</button>".format(name = current_schedule[1], schedule = current_schedule[0]).encode('utf-8')
            else:
                content = "<h1>Start new Recording</h1><button hx-get=\"/set_time\" hx-target=\"#status\" hx-vars=\"timestamp:currentTimestamp()\">Sync Time</button><form hx-get=\"/start_recording\" hx-target=\"#status\" hx-vars=\"timestamp:currentTimestamp()\"><div><label>Recording Name:</label><input type=\"text\" name=\"name\" value=\"\"></div><div><label>Recording Schedule:</label><input type=\"text\" name=\"schedule\" value=\"\"></div><button>Start Recording</botton></form>".encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
    
    return StreamingHandler

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def run_frontend(port: int, camera_control: CameraControl):
    try:
        address = ('', port)
        server = StreamingServer(address, streaming_handler(camera_control))
        logger.info("starting frontend")
        server.serve_forever()
    finally:
        logger.info("shutting down frontend")