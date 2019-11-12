import os
import shutil

from avocado.utils import process


def get_pool_helper(pool):
    return FsCli(pool.target.path)


class FsCli(object):

    def __init__(self, dir_path):
        self.dir_path = dir_path
        self._is_export = None
        self._protocol = r"file://"

    def create(self):
        if not self.is_exists:
            os.makedirs(self.dir_path)
        self._is_export = True

    def remove(self):
        if os.path.isdir(self.dir_path):
            shutil.rmtree(self.dir_path)
        self._is_export = False

    @staticmethod
    def remove_file(path):
        return process.system("rm -f %s" % path, shell=True)

    def get_path_by_name(self, name):
        path = os.path.join(self.dir_path, name)
        return os.path.realpath(path)

    def get_url_by_name(self, name):
        path = self.get_path_by_name(name)
        return self.path_to_url(path)

    def list_files(self, _root=None):
        """List all files in top directory"""

        def _list_files(_dir):
            for root, dirs, files in os.walk(_dir):
                for f in files:
                    path = os.path.join(root, f)
                    yield os.path.realpath(path)
                for d in dirs:
                    _d = os.path.join(root, d)
                    _list_files(_d)

        root_dir = _root or self.dir_path
        return _list_files(root_dir)

    @staticmethod
    def get_size(path):
        """Get file size"""
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    def path_to_url(self, path):
        """Get url schema path"""
        return "%s%s" % (self._protocol, os.path.realpath(path))

    def url_to_path(self, url):
        return url[len(self._protocol):]

    @property
    def is_exists(self):
        if self._is_export is None:
            self._is_export = os.path.isdir(self.dir_path)
        return self._is_export

    @property
    def capacity(self):
        cmd = "df -k --output=size %s |tail -n1" % self.dir_path
        output = process.system_output(cmd, shell=True)
        return int(output) * 1024

    @property
    def available(self):
        cmd = "df -k --output=avail %s |tail -n1" % self.dir_path
        output = process.system_output(cmd, shell=True)
        return int(output) * 1024
