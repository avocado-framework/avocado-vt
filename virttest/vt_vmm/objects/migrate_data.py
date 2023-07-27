class LiveMigrateData(object):
    def __init__(self):
        pass


class QemuLiveMigrateData(object):
    def __init__(self):
        self._protocol = None
        self._remote_port = None
        self._capabilities = None
        self._parameters = None
        self._fd = None


class LibvirtLiveMigrateData(object):
    def __init__(self):
        pass
