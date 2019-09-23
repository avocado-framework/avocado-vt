from virttest.storage.storage_volume.volume_format import SUPPORTED_VOLUME_FORMAT
from virttest.storage.storage_volume.volume_protocol import SUPPORTED_VOLUME_PROTOCOL


class UnsupportedVolumeFormatException(Exception):
    """"""

    def __init__(self, fmt):
        self.fmt = fmt
        self.message = "Unsupported volume format '%s', supported format are: %s" % (
            self.fmt, SUPPORTED_VOLUME_FORMAT)

    def __str__(self):
        return "UnsupportedVolumeFormatException:%s" % self.message


class UnsupportedVolumeProtocolException(Exception):
    """"""

    def __init__(self, protocol):
        self.protocol = protocol
        self.message = "Unsupported volume protocol '%s', supported protocol are: %s" % (
            self.protocol, SUPPORTED_VOLUME_PROTOCOL)

    def __str__(self):
        return "UnsupportedVolumeProtocolException:%s" % self.message
