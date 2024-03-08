from .. import _CVMResBackingMgr
from .. import _all_subclasses


class LaunchSecurity(object):
    _instance = None

    @classmethod
    def dispatch(cls):
        return cls._instance

    @classmethod
    def startup(cls, config):
        if cls._instance is not None:
            return cls._instance

        for mgr_cls in _all_subclasses(_CVMResBackingMgr):
            if mgr_cls.get_platform_flags() is not None:
                cls._instance = mgr_cls(config)
                cls._instance.startup()
                return cls._instance

        raise

    @classmethod
    def teardown(cls):
        cls._instance.teardown()
