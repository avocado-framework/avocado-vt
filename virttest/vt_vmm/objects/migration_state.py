from enum import Enum, auto


class MigrationState(Enum):
    ACCEPTED = auto
    PRE_MIGRATING = auto
    MIGRATING = auto
    PAUSED_MIGRATING = auto
    COMPLETED = auto
    POST_MIGRATING = auto
    ERROR = auto
