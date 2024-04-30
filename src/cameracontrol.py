from threading import Condition
from typing import Optional
from streaming.output import StreamingOutput
from recorder import RecorderOutput
from clock import Clock
from schedule import Schedule
import time

import cv2
from picamera2 import MappedArray, Picamera2
from picamera2.encoders import MJPEGEncoder, H264Encoder
from picamera2.outputs import FileOutput

class CameraControl:
    def __init__(self):
        self._clock: Clock = Clock()
        self._schedule = Schedule(self._clock)
        self.streaming_output = StreamingOutput()
        self._stream_encoder = MJPEGEncoder()
        self._stream_encoder.output = FileOutput(self.streaming_output)
        self._recording_encoder = H264Encoder()
        self._recording_encoder.output = RecorderOutput(self._schedule)
        self._picamera = Picamera2()

        self._stream_count = 0
        self._recording_encoder_active: bool = False
        self._condition = Condition()

        video_config = self._picamera.create_video_configuration()
        self._picamera.configure(video_config)

        colour = (255, 255, 255)
        origin = (0, 30)
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 1
        thickness = 2

        def apply_timestamp(request):
            timestamp = self._clock.get_time_string()
            with MappedArray(request, "main") as m:
                cv2.putText(m.array, timestamp, origin, font, scale, colour, thickness)

        self._picamera.pre_callback = apply_timestamp

    def set_time(self, timestamp: int):
        self._clock.set_time(timestamp)

    def new_stream(self):
        with self._condition:
            if self._stream_count == 0:
                if not self._recording_encoder_active:
                    self._picamera.start()
                self._picamera.start_encoder(self._stream_encoder)
            self._stream_count = self._stream_count + 1

    def end_stream(self):
        with self._condition:
            self._stream_count = self._stream_count - 1
            if self._stream_count == 0:
                self._picamera.stop_encoder(self._stream_encoder)
                if not self._recording_encoder_active:
                    self._picamera.stop()

    def record(self, name: str, schedule: str) -> Optional[str]:
        error = self._schedule.set_schedule(name = name, ranges_str = schedule)
        if self._schedule.should_run_encoder():
            self._run_recording_encoder()
        return error
    
    def stop_recording(self):
        self._schedule.stop_recording()
        self._stop_recording_encoder()

    def get_schedule(self) -> Optional[tuple[str, str]]:
        return self._schedule.get_schedule()

    def camera_loop(self):
        while True:
            if self._schedule.should_run_encoder():
                self._run_recording_encoder()
            else:
                self._stop_recording_encoder()
            time.sleep(60)

    def _run_recording_encoder(self):
        with self._condition:
            if self._recording_encoder_active:
                return
            self._recording_encoder_active = True
            if self._stream_count == 0:
                self._picamera.start()
            self._picamera.start_encoder(self._recording_encoder)

    def _stop_recording_encoder(self):
        with self._condition:
            if not self._recording_encoder_active:
                return
            self._recording_encoder_active = False
            self._picamera.stop_encoder(self._recording_encoder)
            if self._stream_count == 0:
                self._picamera.stop()
