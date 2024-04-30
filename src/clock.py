
import time
from datetime import datetime, timezone

class Clock():
    def __init__(self):
        self.offset: int = 0
    
    def get_timestamp(self) -> int:
        return time.clock_gettime_ns(time.CLOCK_BOOTTIME) + self.offset
    
    def get_time_string(self) -> str:
        ts = self.get_timestamp()
        return datetime.fromtimestamp(ts/1000000000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    def set_time(self, timestamp: int):
        self.offset = timestamp - time.clock_gettime_ns(time.CLOCK_BOOTTIME)
