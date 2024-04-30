from threading import Condition
from typing import Optional
from datetime import datetime, timezone
from clock import Clock

DAY_DURATION = 24*60*60*1000000000
RECORD_DURATION = 60*60*1000000000 # 1 hour

CLOSE_DURATION = 3*60*1000000000 # 3 min

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
    
    def is_close(self, timestamp: int) -> bool:
        timeonly_begin = timestamp + CLOSE_DURATION % DAY_DURATION
        timeonly_end = timestamp % DAY_DURATION
        if (timeonly_begin < self._begin):
            return False
        if (timeonly_end >= self._end):
            return False
        return True

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
    def __init__(self, clock: Clock):
        self._ranges: list[TimeRange] = []
        self._name: str = ""
        self._condition = Condition()
        self._clock: Clock = clock

    def set_schedule(self, ranges_str: str, name: str) -> Optional[str]:
        try:
            ranges: list[TimeRange] = self._parse_timeranges(ranges_str)
        except Exception as error:
            return str(error)
        
        # logger.info(ranges)

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

    def should_record(self) -> Optional[str]:
        timestamp = self._clock.get_timestamp()
        with self._condition:
            current_ranges = self._ranges
            current_name = self._name
        for range in current_ranges:
            start = range.start(timestamp)
            if (start is not None):
                #return start
                return current_name + '-' + datetime.fromtimestamp(start/1000000000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        return None
    
    def should_run_encoder(self) -> bool:
        timestamp = self._clock.get_timestamp()
        with self._condition:
            current_ranges = self._ranges
        for range in current_ranges:
            if range.is_close(timestamp):
                return True
        return False
    
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
