from .. import _ResBacking
from .. import _ResBackingCaps
from .. import _CVMResBackingMgr


class _SEVCommResBacking(_ResBacking):

    def __init__(self, requests):
        super().__init__(requests)
        self._cbitpos = None
        self._reduced_phys_bits = None
        # self._sev_device = '/dev/sev'
        # self._kernel_hashes = None

    def to_specs(self):
        return {"cbitpos": self._cbitpos, "reduced-phys-bits": self._reduced_phys_bits}


class _SEVResBacking(_SEVCommResBacking):
    RESOURCE_TYPE = "sev"

    def __init__(self):
        super().__init__()
        self._dh_cert = None
        self._session = None

    def allocate(self, requests):
        pass

    def free(self):
        pass

    def to_specs(self):
        pass


class _SNPResBacking(_SEVCommResBacking):
    RESOURCE_TYPE = "snp"

    def __init__(self):
        super().__init__()

    def allocate(self, requests):
        pass

    def free(self):
        pass

    def to_specs(self):
        pass


class _SEVResBackingCaps(_ResBackingCaps):

    def __init__(self, params):
        self._cbitpos = None
        self._reduced_phys_bits = None
        self._sev_device = None
        self._max_sev_guests = None
        self._max_snp_guests = None
        self._pdh = None
        self._cert_chain = None
        self._cpu0_id = None

    def load(self):
        pass

    def is_capable(self, requests):
        pass

    def increase(self, backing):
        pass

    def decrease(self, backing):
        pass

    @property
    def max_sev_guests(self):
        return self._max_sev_guests

    @property
    def max_snp_guests(self):
        return self._max_snp_guests


class _SEVResBackingMgr(_CVMResBackingMgr):

    def __init__(self, config):
        super().__init__(config)
        self._caps = _SEVResBackingCaps(config)
        _SEVResBackingMgr._platform_flags = config

    def startup(self):
        reset_sev_platform()
        super().startup()

    def teardown(self):
        reset_sev_platform()
