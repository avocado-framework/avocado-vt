from ..image import _Image


class _QemuImage(_Image):

    _IMAGE_TYPE = "qemu"

    def _initialize(self, config):
        super()._initialize(config)
        spec = config["spec"]
        self._size = spec["size"]
        self._format = spec["format"]

    def create(self):
        pass

    def destroy(self):
        pass

    def convert(self, target_id):
        pass

    def rebase(self, backing_id):
        pass

    def commit(self, backing_id):
        pass

    def snapshot_create(self):
        pass

    def snapshot_del(self, blkdebug_cfg=""):
        pass

    def snapshot_list(self, force_share=False):
        pass

    def snapshot_apply(self):
        pass

    def bitmap_add(self, bitmap_name):
        pass

    def bitmap_remove(self, bitmap_name):
        pass

    def bitmap_clear(self, bitmap_name):
        pass

    def bitmap_enable(self, bitmap_name):
        pass

    def bitmap_disable(self, bitmap_name):
        pass

    def bitmap_merge(self, bitmap_name_source, bitmap_name_target, bitmap_image_source):
        pass

    def info(self, force_share=False, output="human"):
        pass

    def compare(self, target_id, strict_mode=False, verbose=True, force_share=False):
        pass

    def check(self, force_share=False):
        pass

    def amend(self, cache_mode=None, ignore_status=False):
        pass

    def resize(self, size, shrink=False, preallocation=None):
        pass

    def map(self, output="human"):
        pass

    def measure(self, target_fmt, size=None, output="human"):
        pass

    def dd(self, target_id, bs=None, count=None, skip=None):
        pass
