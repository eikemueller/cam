import io
from threading import Condition
from typing import Optional

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame: Optional[bytes] = None
        self.condition = Condition()

    def write(self, buf: Optional[bytes]):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()
