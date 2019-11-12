from virttest import utils_misc


class StorageVolume(object):

    def __init__(self, pool, name=None, _format="raw"):
        self.name = name
        self.pool = pool
        self._url = None
        self._path = None
        self._capacity = None
        self._backing_store = None
        self._key = None
        self._auth = None
        self.format = _format
        self.is_allocated = None
        self.encryption = None
        self.preallocation = None
        self.used_by = []
        self.pool.add_volume(self)

    @property
    def url(self):
        if self._url is None:
            if self.name and hasattr(self.pool.helper, "get_url_by_name"):
                url = self.pool.helper.get_url_by_name(self.name)
                self._url = url
        return self._url

    @url.setter
    def url(self, url):
        self._url = url

    @property
    def path(self):
        if self._path is None:
            if self.url and hasattr(self.pool.helper, "url_to_path"):
                path = self.pool.helper.url_to_path(self.url)
                self._path = path
        return self._path

    @path.setter
    def path(self, path):
        self._path = path

    @property
    def key(self):
        if self._key is None:
            if self.pool.TYPE in ("directory", "nfs"):
                self._key = self.path
            else:
                self._key = self.url
        return self._key

    @key.setter
    def key(self, key):
        self._key = key

    @property
    def capacity(self):
        if self._capacity is None:
            if self.key and hasattr(self.pool.helper, "get_size"):
                self._capacity = self.pool.get_size(self.key)
        return int(self._capacity)

    @capacity.setter
    def capacity(self, size):
        self._capacity = float(
            utils_misc.normalize_data_size(
                str(size), 'B', '1024'))

    @property
    def backing_store(self):
        return self._backing_store

    @backing_store.setter
    def backing_store(self, backing):
        if self.format == "qcow2":
            self._backing_store = backing
        else:
            self._backing_store = None

    @property
    def auth(self):
        if self._auth is None:
            if self.pool.source:
                self._auth = self.pool.source.auth
        return self._auth

    def info(self):
        out = dict()
        out["name"] = self.name
        out["pool"] = str(self.pool)
        out["url"] = self.url
        out["path"] = self.path
        out["key"] = self.key
        out["format"] = self.format
        out["auth"] = str(self.auth)
        out["capacity"] = self.capacity
        out["backing_store"] = str(self.backing_store)
        out["encryption"] = str(self.encryption)
        out["preallocation"] = self.preallocation
        return out

    def generate_qemu_img_options(self):
        options = " -f %s" % self.format
        if self.format == "qcow2" and self.backing_store:
            options += " -b %s" % self.backing_store.key
        if self.encryption:
            secret = self.encryption.secret
            encryption_format = self.encryption.format
            options += " --object secret,data=%s,id=%s" % (
                secret.data, secret.name)
            options += " -o encrypt.format=%s,encrypt.key-secret=%s" % (
                encryption_format, secret.name)
        return options

    def __str__(self):
        return "%s: %s, %s" % (self.__class__.__name__,
                               self.name, str(self.key))

    def __eq__(self, vol):
        return self.info() == vol.info()
