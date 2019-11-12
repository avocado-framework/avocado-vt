import os

from gluster import gfapi


def get_pool_helper(pool):
    volname = pool.source.name
    root_dir = pool.source.dir_path or '/'
    host = pool.source.hosts[0].hostname
    port = pool.source.hosts[0].port or 24007
    return GlusterCli(host, volname, port, root_dir)


class GlusterCli(object):

    def __init__(self, host, volname, port=24007, root_dir='/'):
        self.root_dir = root_dir
        self.host = host
        self.volume = gfapi.Volume(host, volname, port=port)
        self._is_mounted = None
        self._base_url = "gluster://%s:%s/%s" % (
            self.host, self.volume.port, self.volume.volname)

    def list_files(self):
        def _list_files(_dir):
            for root, dirs, files in self.volume.walk(_dir):
                for f in files:
                    yield os.path.join(root, f)
                for d in dirs:
                    _list_files(os.path.join(root, d))

        self.mount()
        if not self.volume.isdir(self.root_dir):
            self.volume.makedirs(self.root_dir)
        return _list_files(self.root_dir)

    def url_to_path(self, url):
        return url[len(self._base_url):]

    def path_to_url(self, path):
        return self._base_url + path

    def get_url_by_name(self, name):
        path = os.path.join(self.root_dir, name)
        return "%s%s" % (self._base_url, path)

    def get_size(self, url):
        path = url.lstrip(self._base_url)
        try:
            return self.volume.getsize(path)
        except OSError:
            return 0

    def mount(self):
        if not self.is_mounted:
            self.volume.mount()
            self._is_mounted = True

    def umount(self):
        if self.is_mounted:
            self.volume.umount()
            self._is_mounted = False

    def remove(self):
        self.mount()
        self.volume.rmtree(self.root_dir, ignore_errors=True)

    def remove_image(self, url):
        self.mount()
        path = self.url_to_path(url)
        self.volume.remove(path)

    @property
    def is_mounted(self):
        if self._is_mounted is None:
            self._is_mounted = self.volume.mounted
        return self._is_mounted

    @property
    def capacity(self):
        stat = self.volume.statvfs(self.root_dir)
        return stat.f_blocks * stat.f_frsize

    @property
    def available(self):
        stat = self.volume.statvfs(self.root_dir)
        return stat.f_bfree * stat.f_frsize
