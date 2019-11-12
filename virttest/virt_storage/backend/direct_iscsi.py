from avocado.core import exceptions

from virttest.virt_storage import storage_volume
from virttest.virt_storage.backend import base
from virttest.virt_storage.utils import storage_util


class IscsiDriectPool(base.BaseStoragePool):
    TYPE = "iscsi-direct"

    def find_sources(self):
        """find lun in iscsi target"""
        # Used host path as key of the volume
        return self.helper.list_disks()

    def start(self):
        self.helper.login()
        self.refresh()

    def stop(self):
        self.helper.logout()

    def refresh(self):
        for path in self.find_sources():
            if self.find_volume_by_path(path):
                continue
            else:
                self.create_volume_from_path(path)

    def create_volume_from_path(self, path):
        capacity = self.helper.get_size(path)
        url = self.helper.path_to_url(path)
        volume = storage_volume.StorageVolume(self)
        volume.path = path
        volume.url = url
        volume.capacity = capacity
        volume.is_allocated = True
        return volume

    def create_volume(self, volume):
        """map exists lun to volume object"""
        vol = self.__find_appropriate_lun(volume)
        volume.path = vol.path
        volume.url = vol.url
        self._volumes.remove(vol)
        storage_util.create_volume(volume)
        volume.is_allocated = True
        return volume

    def remove_volume(self, volume):
        self._volumes.remove(volume)

    def __find_appropriate_lun(self, vol):
        """find appropriate lun for logical volume"""
        volumes = filter(
            lambda x: x.capacity - vol.capacity >= 0 and x.name is None, self._volumes)
        try:
            return sorted(volumes, key=lambda x: x.capacity)[0]
        except Exception:
            raise exceptions.TestError(
                "No appropriate lun found for volume %s: %s" %
                (vol.name, vol.info()))

    @property
    def available(self):
        free_voluems = filter(lambda x: x.is_allocated and x.name is None, self._volumes)
        return sum(map(lambda x: x.capacity, free_voluems))
