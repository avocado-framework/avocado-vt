from enum import Enum, auto


class States(Enum):
    RUNNING = auto
    STOPPED = auto
    PAUSED = auto
    DEFINED = auto
    UNDEFINED = auto
    SUSPENDED = auto
    ERROR = auto
