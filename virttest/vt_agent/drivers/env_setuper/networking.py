import os.path

from vt_agent.core import data_dir as core_data_dir

from .core import Setuper
from .core import SetuperError

from virttest import ip_sniffing


class IPSniffer(Setuper):
    def __init__(self):
        super(IPSniffer, self).__init__("ip_sniffer")
        self._sniffer = None
        self._cache = ip_sniffing.AddrCache()

    @property
    def cache(self):
        return self._cache

    def setup(self, setup_confi={}):
        # Start ip sniffing if it isn't already running
        # The fact it has to be started here is so that the test params
        # have to be honored.
        sniffers = ip_sniffing.Sniffers

        for s_cls in sniffers:
            if s_cls.is_supported():
                log_file = os.path.join(core_data_dir.get_ip_sniffer_log_dir(), "ip-sniffer.log")
                self._sniffer = s_cls(self._cache, log_file)
                break

        if not self._sniffer:
            raise SetuperError(
                "Can't find any supported ip sniffer! "
                "%s" % [s.command for s in sniffers]
            )

        self._sniffer.start()

    def cleanup(self, cleanup_config={}):
        # Terminate the ip sniffer thread
        if self._sniffer:
            self._sniffer.stop()
