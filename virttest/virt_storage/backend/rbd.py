from virttest.virt_storage import storage_volume
from virttest.virt_storage.backend import base
from virttest.virt_storage.utils import storage_util


class RbdPool(base.BaseStoragePool):
    TYPE = 'rbd'

    def find_sources(self):
        return map(self.helper.get_url_by_name, self.helper.list_images())

    def start(self):
        self.helper.connect()
        self.refresh()

    def stop(self):
        return self.helper.shutdown()

    def refresh(self):
        urls = filter(lambda x: not self.find_volume_by_url(x), self.find_sources())
        return list(map(self.create_volume_from_remote, urls))

    def create_volume_from_remote(self, url):
        volume = storage_volume.StorageVolume(self)
        volume.path = volume.url = url
        volume.capacity = self.helper.get_size(url)
        volume.is_allocated = True
        return volume

    def create_volume(self, volume):
        if volume.url is None:
            url = self.helper.get_url_by_name(volume.name)
            volume.url = volume.path = url
        if volume.is_allocated:
            self.helper.remove_image(volume.url)
        storage_util.create_volume(volume)
        volume.is_allocated = True
        return volume

    def remove_volume(self, volume):
        self.helper.remove_image(volume.url)
        self._volumes.remove(volume)
