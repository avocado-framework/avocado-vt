#!/usr/bin/python
"""
Library used to provide the appropriate data dir for virt test.
"""
import inspect
import logging
import os
import glob
import shutil
import stat

import pkg_resources

from avocado.core import data_dir
from avocado.utils import distro
from avocado.utils import path as utils_path

from virttest.compat import get_settings_value

from six.moves import xrange

BASE_BACKEND_DIR = pkg_resources.resource_filename('virttest', 'backends')
TEST_PROVIDERS_DIR = pkg_resources.resource_filename('virttest', 'test-providers.d')
SHARED_DIR = pkg_resources.resource_filename('virttest', 'shared')
DEPS_DIR = os.path.join(SHARED_DIR, 'deps')
BASE_DOWNLOAD_DIR = os.path.join(SHARED_DIR, 'downloads')

DATA_DIR = os.path.join(data_dir.get_data_dir(), 'avocado-vt')
DOWNLOAD_DIR = os.path.join(DATA_DIR, 'downloads')
BACKING_DATA_DIR = None


LOG = logging.getLogger('avocado.' + __name__)


class MissingDepsDirError(Exception):
    pass


class UnknownBackendError(Exception):

    def __init__(self, backend):
        self.backend = backend

    def __str__(self):
        return ("Virt Backend %s is not currently supported by avocado-vt. "
                "Check for typos and the list of supported backends" %
                self.backend)


class SubdirList(list):

    """
    List of all non-hidden subdirectories beneath basedir
    """

    def __in_filter__(self, item):
        if self.filterlist:
            for _filter in self.filterlist:
                if item.count(str(_filter)):
                    return True
            return False
        else:
            return False

    def __set_initset__(self):
        for dirpath, dirnames, filenames in os.walk(self.basedir):
            del filenames  # not used
            # Don't modify list while in use
            del_list = []
            for _dirname in dirnames:
                if _dirname.startswith('.') or self.__in_filter__(_dirname):
                    # Don't descend into filtered or hidden directories
                    del_list.append(_dirname)
                else:
                    self.initset.add(os.path.join(dirpath, _dirname))
            # Remove items in del_list from dirnames list
            for _dirname in del_list:
                del dirnames[dirnames.index(_dirname)]

    def __init__(self, basedir, filterlist=None):
        self.basedir = os.path.abspath(str(basedir))
        self.initset = set([self.basedir])  # enforce unique items
        self.filterlist = filterlist
        self.__set_initset__()
        super(SubdirList, self).__init__(self.initset)


class SubdirGlobList(SubdirList):

    """
    List of all files matching glob in all non-hidden basedir subdirectories
    """

    def __initset_to_globset__(self):
        globset = set()
        for dirname in self.initset:  # dirname is absolute
            pathname = os.path.join(dirname, self.globstr)
            for filepath in glob.glob(pathname):
                if not self.__in_filter__(filepath):
                    globset.add(filepath)
        self.initset = globset

    def __set_initset__(self):
        super(SubdirGlobList, self).__set_initset__()
        self.__initset_to_globset__()

    def __init__(self, basedir, globstr, filterlist=None):
        self.globstr = str(globstr)
        super(SubdirGlobList, self).__init__(basedir, filterlist)


def get_backing_data_dir():
    return DATA_DIR


BACKING_DATA_DIR = get_backing_data_dir()


def get_root_dir():
    return os.path.dirname(BASE_BACKEND_DIR)


def get_data_dir():
    return DATA_DIR


def get_shared_dir():
    return SHARED_DIR


def get_base_backend_dir():
    return BASE_BACKEND_DIR


def get_local_backend_dir():
    return os.path.join(get_data_dir(), 'backends')


def get_backend_dir(backend_type):
    if backend_type not in os.listdir(BASE_BACKEND_DIR):
        raise UnknownBackendError(backend_type)
    return os.path.join(get_local_backend_dir(), backend_type)


def get_backend_cfg_path(backend_type, cfg_basename):
    return os.path.join(get_backend_dir(backend_type), 'cfg', cfg_basename)


def get_deps_dir(target=None):
    """
    For a given test provider, report the appropriate deps dir.

    The little inspect trick is used to avoid callers having to do
    sys.modules[] tricks themselves.

    :param target: File we want in deps folder. Will return the path to the
                   target if set and available. Or will only return the path
                   to dep folder.
    """
    # Get the frame that called this function
    frame = inspect.stack()[1]
    # This is the module that called the function
    # With the module path, we can keep searching with a parent dir with 'deps'
    # in it, which should be the correct deps directory.
    try:
        module = inspect.getmodule(frame[0])
        path = os.path.dirname(module.__file__)
    except TypeError:
        path = os.path.dirname(frame[1])
    nesting_limit = 10
    for index in xrange(nesting_limit):
        files = os.listdir(path)
        origin_path = ""
        if 'shared' in files:
            origin_path = path
            path = os.path.join(path, 'shared')
            files = os.listdir(path)
        if 'deps' in files:
            deps = os.path.join(path, 'deps')
            if target:
                if target in os.listdir(deps):
                    return os.path.join(deps, target)
            else:
                return deps
        if '.git' in os.listdir(path):
            raise MissingDepsDirError("Could not find specified deps dir for "
                                      "git repo %s" % path)
        if origin_path:
            path = origin_path
        path = os.path.dirname(path)
    raise MissingDepsDirError("Could not find specified deps dir after "
                              "looking %s parent directories" %
                              nesting_limit)


def get_tmp_dir(public=True):
    """
    Get the most appropriate tmp dir location.

    :param public: If public for all users' access
    """
    persistent_dir = get_settings_value('vt.common', 'tmp_dir',
                                        default="")
    if persistent_dir != "":
        return persistent_dir
    tmp_dir = None
    # apparmor deny /tmp/* /var/tmp/* and cause failure across tests
    # it is better to handle here
    if distro.detect().name == 'Ubuntu':
        tmp_dir = "/var/lib/libvirt/images"
        if not utils_path.usable_rw_dir(tmp_dir):
            LOG.warning("Unable to write in '/var/lib/libvirt/images' "
                        "on Ubuntu, apparmor might complain...")
            tmp_dir = None
    tmp_dir = data_dir.get_tmp_dir(basedir=tmp_dir)
    if public:
        tmp_dir_st = os.stat(tmp_dir)
        os.chmod(tmp_dir, tmp_dir_st.st_mode | stat.S_IXUSR |
                 stat.S_IXGRP | stat.S_IXOTH | stat.S_IRGRP | stat.S_IROTH)
    return tmp_dir


def get_base_download_dir():
    return BASE_DOWNLOAD_DIR


def get_download_dir():
    return DOWNLOAD_DIR


TEST_PROVIDERS_DOWNLOAD_DIR = os.path.join(get_data_dir(),
                                           'virttest',
                                           'test-providers.d',
                                           'downloads')


def get_base_test_providers_dir():
    return TEST_PROVIDERS_DIR


def get_test_providers_dir():
    """
    Return the base test providers dir (at the moment, test-providers.d).
    """
    return os.path.dirname(TEST_PROVIDERS_DOWNLOAD_DIR)


def get_test_provider_dir(provider):
    """
    Return a specific test providers dir, inside the base dir.
    """
    return os.path.join(TEST_PROVIDERS_DOWNLOAD_DIR, provider)


def clean_tmp_files():
    tmp_dir = get_tmp_dir()
    if os.path.isdir(tmp_dir):
        hidden_paths = glob.glob(os.path.join(tmp_dir, ".??*"))
        paths = glob.glob(os.path.join(tmp_dir, "*"))
        for path in paths + hidden_paths:
            shutil.rmtree(path, ignore_errors=True)


if __name__ == '__main__':
    print("root dir:         " + get_root_dir())
    print("tmp dir:          " + get_tmp_dir())
    print("data dir:         " + DATA_DIR)
    print("deps dir:         " + DEPS_DIR)
    print("backing data dir: " + BACKING_DATA_DIR)
    print("test providers dir: " + TEST_PROVIDERS_DIR)
