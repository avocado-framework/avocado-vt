import tempfile
import time

import rados
import rbd


def get_pool_helper(pool):
    if not pool.source.hosts:
        ceph_conf = '/etc/ceph/ceph.conf'
        ceph_keyring = '/etc/ceph/ceph.keyring'
    else:
        key = pool.source.auth.password
        mon_host = pool.source.hosts[0].hostname
        user = pool.source.auth.username or "client.admin"
        ceph_conf = tempfile.mktemp()
        ceph_keyring = tempfile.mktemp()

        with open(ceph_conf, "w") as fd:
            fd.writelines(["[global]", "mon host = %s" % mon_host])
        with open(ceph_keyring, "w") as fd:
            fd.writelines(["[%s]" % user, "key = %s" % key])

    conf = {"keyring": ceph_keyring}
    pool_name = pool.source.name
    return RbdCli(ceph_conf, conf, pool_name)


class RbdCli(object):
    def __init__(self, conffile, conf, pool):
        self.cluster = rados.Rados(conffile=conffile, conf=conf)
        self._pool = pool
        self._is_connect = False
        self._protocol = "rbd:"
        self._base_url = "%s%s/" % (self._protocol, self._pool)

    def list_images(self):
        self.connect()
        if self.cluster.pool_exists(self._pool):
            with self.cluster.open_ioctx(self._pool) as ioctx:
                return sorted(rbd.RBD().list(ioctx))
        return []

    def get_url_by_name(self, image):
        return "%s%s" % (self._base_url, image)

    def url_to_path(self, url):
        if url.startswith(self._protocol):
            return url[len(self._protocol):]
        return url

    def get_size(self, image):
        if not self.is_image_exists(image):
            return 0
        name = self._get_image_name(image)
        with self.cluster.open_ioctx(self._pool) as ioctx:
            time.sleep(0.3)
            with rbd.Image(ioctx, name) as rbd_image:
                return rbd_image.size()

    def create_image(self, image, size):
        if self.is_image_exists(image):
            return
        name = self._get_image_name(image)
        with self.cluster.open_ioctx(self._pool) as ioctx:
            rbd_inst = rbd.RBD()
            rbd_inst.create(ioctx, name, size)

    def remove_image(self, image, timeout=120):
        if not self.is_image_exists(image):
            return
        name = self._get_image_name(image)
        with self.cluster.open_ioctx(self._pool) as ioctx:
            rbd_inst = rbd.RBD()
            start = time.time()
            end = start + timeout
            while time.time() < end:
                try:
                    rbd_inst.remove(ioctx, name)
                except rbd.ImageBusy:
                    time.sleep(0.3)
                except rbd.ImageNotFound:
                    break

    def is_image_exists(self, path):
        name = self._get_image_name(path)
        return name in self.list_images()

    def _get_image_name(self, path):
        if path.startswith(self._base_url):
            return path.lstrip(self._base_url)
        return path

    def connect(self):
        if not self.is_connected:
            self.cluster.connect()
        self._is_connect = True

    def shutdown(self):
        if self.is_connected:
            self.cluster.shutdown()
        self._is_connect = False

    @property
    def is_connected(self):
        return self._is_connect

    @property
    def capacity(self):
        self.connect()
        stats = self.cluster.get_cluster_stats()
        return stats['kb'] * 1024

    @property
    def available(self):
        self.connect()
        stats = self.cluster.get_cluster_stats()
        return stats['kb_avail'] * 1024
