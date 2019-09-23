class UnsupportedStoragePoolException(Exception):

    def __init__(self, sp_manager, sp_type):
        self.sp_manager = sp_manager
        self.sp_type = sp_type
        self.message = "Unsupported StoragePool type '%s', supported type are: %s" % (
            self.sp_type, sp_manager.supported_storage_backend.keys())

    def __str__(self):
        return "UnsupportedStoragePoolException:%s" % self.message
