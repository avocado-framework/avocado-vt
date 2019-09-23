
class Luks(object):
    
    fmt = "luks"

    def __init__(self, name, params):
        self.key_secret_id = params.get("key_secret_id")
        self.key_secret_data = params.get("key_secret_data")


class Qcow2(object):
 
    fmt = "qcow2"

    def __init__(self, name, params):
        self.name = name
        self.lazy_refcounts = params.get("lazy_refcounts")
        self.pass_discard_request = params.get("pass_discard_request")
        self.pass_discard_snapshot = params.get("pass_discard_snapshot")
        self.pass_discard_other = params.get("pass_discard_other")
        self.overlap_check = params.get("overlap_check")
        self.cache_size = params.get("cache_size")
        self.l2_cache_size = params.get("l2_cache_size")
        self.l2_cache_entry_size = params.get("l2_cache_entry_size")
        self.refcount_cache_size = params.get("refcount_cache_size")
        self.cache_clean_interval = params.get("cache_clean_interval")
        self.encrypt = params.get("encrypt")
        self.data_file = params.get("data_file")
        self.file = None


class Raw(object):

    fmt = "raw"

    def __init__(self, name, params):
        self.name = name
        self.size = params.get("size")
        self.off = params.get("offset")


SUPPORTED_VOLUME_FORMAT = {"qcow2": Qcow2, "raw": Raw, "luks": Luks}
