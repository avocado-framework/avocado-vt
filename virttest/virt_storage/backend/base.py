import re
import uuid

from virttest.virt_storage import utils
from virttest.virt_storage import virt_source
from virttest.virt_storage import virt_target


class BaseStoragePool(object):
    TYPE = "none"

    def __init__(self, name):
        self.name = name
        self.uuid = uuid.uuid1()
        self.source = None
        self.target = None
        self._capacity = None
        self._available = None
        self._helper = None
        self._volumes = set()

    @property
    def capacity(self):
        if self._capacity is None:
            self._capacity = self.helper.capacity
        return self._capacity

    @property
    def available(self):
        if self._available is None:
            self._available = self.helper.available
        return self._available

    @property
    def helper(self):
        if self._helper is None:
            self._helper = utils.get_pool_helper(self)
        return self._helper

    @classmethod
    def pool_define_by_params(cls, name, params):
        inst = cls(name)
        inst.target = virt_target.PoolTarget.target_define_by_params(params)
        if params.get("source"):
            source_params = params.object_params(params.get("source"))
            inst.source = virt_source.PoolSource.source_define_by_params(
                params.get("source"), source_params)
        inst.set_special_opts_by_params(params)
        return inst

    def set_special_opts_by_params(self, params):
        pattern = re.compile(r"(\w+)\s*=(\w+)\s*")
        options = params.get("config_opts", "").split(",")
        for option in options:
            match = pattern.search(option)
            if match:
                key, val = match.groups()
                setattr(self, key, val)

    def start(self):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def destroy(self):
        """Destroy storage pools"""
        self.stop()
        self._volumes.clear()

    def find_sources(self):
        raise NotImplementedError

    def create_volume(self, volume):
        raise NotImplementedError

    def refresh(self):
        raise NotImplementedError

    def remove_volume(self, volume):
        raise NotImplementedError

    def find_volume_by_name(self, name):
        """find volume by name"""
        return self.__find_volume_by_attr("name", name)

    def find_volume_by_path(self, path):
        """find volume by path"""
        return self.__find_volume_by_attr("path", path)

    def find_volume_by_key(self, key):
        """find volume by key"""
        return self.__find_volume_by_attr("key", key)

    def find_volume_by_url(self, url):
        """find volume by url"""
        return self.__find_volume_by_attr("url", url)

    def __find_volume_by_attr(self, attr, val):
        """
        Find the volume attribute is match given value

        :param attr:  attribute name
        :param val: attribute value
        :return:  StorageVolume object or None
        :raise:
        """

        matched_volumes = filter(
            lambda x: str(
                getattr(
                    x,
                    attr)) == str(val),
            self.get_volumes())
        return matched_volumes[0] if matched_volumes else None

    def get_volumes(self):
        return self._volumes

    def add_volume(self, volume):
        self._volumes.add(volume)

    def acquire_volume(self, volume):
        if volume.is_allocated:
            return
        self.create_volume(volume)
        self.refresh()

    def info(self):
        out = dict()
        out["name"] = self.name
        out["uuid"] = str(self.uuid)
        out["state"] = self.state
        out["source"] = str(self.source)
        out["target"] = str(self.target)
        out["capacity"] = str(self.capacity)
        out["available"] = str(self.available)
        out["helper"] = str(self.helper)
        out["volumes"] = list(map(str, self._volumes))
        return out

    def __str__(self):
        return "%s:%s" % (self.__class__.__name__, self.name)
