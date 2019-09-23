class StorageVolume(object):

    def __init__(self, name, pool, params):
        self.name = name
        self.params = params
        self.protocol = None
        self.fmt = None
        self.pool = pool
        self.backing = None
