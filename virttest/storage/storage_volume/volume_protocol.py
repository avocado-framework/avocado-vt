

class VolumeProtocol(object):

    def __init__(self, name, pool, params):
        self.name = name
        self.pool = pool
        self.discard = params.get("discard")
        self.cache_direct = params.get("cache_direct")
        self.cache_no_flush = params.get("cache_no_flush")
        self.read_only = params.get("readonly")
        self.auto_read_only = params.get("auto_readonly")
        self.force_share = params.get("force_share")
        self.detect_zeroes = params.get("detect_zeroes")


class VolumeProtocolFile(VolumeProtocol):

    def __init__(self, name, pool, params):
        super(VolumeProtocolFile, self).__init__(name, pool, params)
        self.filename = params["image_filename"]


class VolumeProtocolGluster(VolumeProtocol):
    protocol = "gluster"

    def __init__(self, name, pool, params):
        super(VolumeProtocolGluster, self).__init__(name, pool, params)
        self.image_name = params["gluster_image_name"]


class VolumeProtocolDirectIscsi(VolumeProtocol):

    def __init__(self, name, pool, params):
        super(VolumeProtocolDirectIscsi, self).__init__(name, pool, params)
        self.lun = params.get("iscsi_lun", 0)


class VolumeProtocolNfs(VolumeProtocol):

    def __init__(self, name, pool, params):
        super(VolumeProtocolNfs, self).__init__(name, pool, params)
        self.image_name = params["nfs_image_name"]


class VolumeProtocolRbd(VolumeProtocol):

    def __init__(self, name, pool, params):
        super(VolumeProtocolRbd, self).__init__(name, pool, params)
        self.image_name = params["rbd_image_name"]


SUPPORTED_VOLUME_PROTOCOL = {
    "file": VolumeProtocolFile,
    "nfs": VolumeProtocolNfs,
    "iscsi": VolumeProtocolDirectIscsi,
    "gluster": VolumeProtocolGluster,
    "rbd": VolumeProtocolRbd
}
