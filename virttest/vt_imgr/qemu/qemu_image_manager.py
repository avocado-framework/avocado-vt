from ..image_manager import _ImageManager


class _VTQemuImageManager(_ImageManager):

    def __init__(self):
        self._images = dict()  # {image id: image object}

    @classmethod
    def _get_image_class(cls, pool_type):
        pass

    def create(self, image_spec):
        pass

    def destroy(self):
        pass

    def convert(self, source_id, target_id):
        pass

    def rebase(self, top_id, backing_id):
        pass

    def commit(self, top_id, backing_id):
        pass

    def snapshot_create(self):
        pass

    def snapshot_del(self, blkdebug_cfg=""):
        pass

    def snapshot_list(self, force_share=False):
        pass

    def snapshot_apply(self):
        pass

    def bitmap_add(self, image_id, bitmap_name):
        pass

    def bitmap_remove(self, image_id, bitmap_name):
        pass

    def bitmap_clear(self, image_id, bitmap_name):
        pass

    def bitmap_enable(self, image_id, bitmap_name):
        pass

    def bitmap_disable(self, image_id, bitmap_name):
        pass

    def bitmap_merge(
        self, image_id, bitmap_name_source, bitmap_name_target, bitmap_image_source
    ):
        pass

    def info(self, image_id, force_share=False, output="human"):
        pass

    def compare(
        self, source_id, target_id, strict_mode=False, verbose=True, force_share=False
    ):
        pass

    def check(self, image_id, force_share=False):
        pass

    def amend(self, image_id, cache_mode=None, ignore_status=False):
        pass

    def resize(self, image_id, size, shrink=False, preallocation=None):
        pass

    def map(self, image_id, output="human"):
        pass

    def measure(self, target_fmt, size=None, output="human"):
        pass

    def dd(self, source_id, target_id, bs=None, count=None, skip=None):
        pass
