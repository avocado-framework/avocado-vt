class InstanceError(Exception):
    pass


class InstanceInvalidState(InstanceError):
    pass


class InstanceSpecError(InstanceError):
    pass
