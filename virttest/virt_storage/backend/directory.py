from virttest.virt_storage import storage_volume
from virttest.virt_storage.backend import base
from virttest.virt_storage.utils import storage_util


class DirectoryPool(base.BaseStoragePool):
    TYPE = "directory"

    def find_sources(self):
        return self.helper.list_files()

    def start(self):
        self.helper.create()
        self.refresh()

    def stop(self):
        pass

    def delete(self):
        self.helper.remove()

    def refresh(self):
        files = filter(
            lambda x: not self.find_volume_by_path,
            self.find_sources())
        return map(self.create_volume_from_local, files)

    def create_volume_from_local(self, path):
        """
        Create logical volume from local file
        file size maybe mismatch, but need to resize in here
        it will be recreate by qemu-img in next step.

        """
        volume = storage_volume.StorageVolume(self)
        volume.path = path
        volume.url = self.helper.path_to_url(path)
        volume.capacity = self.helper.get_size(path)
        volume.is_allocated = True
        return volume

    def create_volume(self, volume):
        if volume.path is None:
            volume.path = self.helper.get_path_by_name(volume.name)
        storage_util.create_volume(volume)
        volume.is_allocated = True
        return volume

    def remove_volume(self, volume):
        self.helper.remove_file(volume.path)
        self._volumes.remove(volume)
