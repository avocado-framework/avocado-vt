class PoolTarget(object):

    def __init__(self):
        self.path = None
        self.format = None

    @classmethod
    def target_define_by_params(cls, params):
        instance = cls()
        instance.path = params.get("target_path")
        instance.format = params.get("target_format")
        return instance

    def __str__(self):
        return "%s: %s" % (self.__class__.__name__, self.path)
