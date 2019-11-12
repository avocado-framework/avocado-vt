from virttest.virt_storage import storage_volume
from virttest.virt_storage.backend import directory
from virttest.virt_storage.utils import storage_util


class NfsPool(directory.DirectoryPool):
    TYPE = "nfs"

    def find_sources(self):
        files = super(NfsPool, self).find_sources()
        return map(self.helper.path_to_url, files)

    def start(self):
        self.helper.mount()
        self.refresh()

    def stop(self):
        return self.helper.umount()

    def delete(self):
        self.helper.remove()

    def refresh(self):
        urls = filter(
            lambda x: not self.find_volume_by_url,
            self.find_sources())
        return map(self.create_volume_from_remote, urls)

    def create_volume_from_remote(self, url):
        path = self.helper.url_to_path(url)
        capacity = self.helper.get_size(path)
        volume = storage_volume.StorageVolume(self)
        volume.url = url
        volume.path = path
        volume.capacity = capacity
        volume.is_allocated = True
        return volume

    def create_volume(self, volume):
        storage_util.create_volume(volume)
        volume.is_allocated = True
        return volume
