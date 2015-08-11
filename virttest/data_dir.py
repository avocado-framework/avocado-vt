#!/usr/bin/python
"""
Library used to provide the appropriate data dir for virt test.
"""
import inspect
import os
import sys
import glob
import shutil
import tempfile

from avocado.core import data_dir

_SYSTEM_WIDE_ROOT_PATH = '/usr/share/avocado-plugins-vt'
if os.path.isdir(_SYSTEM_WIDE_ROOT_PATH):
    _INSTALLED_SYSTEM_WIDE = len(os.listdir(os.path.join(_SYSTEM_WIDE_ROOT_PATH,
                                                         'shared'))) > 0
else:
    _INSTALLED_SYSTEM_WIDE = False

if _INSTALLED_SYSTEM_WIDE:
    # avocado-vt is installed
    _ROOT_PATH = _SYSTEM_WIDE_ROOT_PATH
else:
    # we're running from source code directories
    _ROOT_PATH = os.path.dirname(os.path.abspath(os.readlink(os.path.dirname(sys.modules['virttest'].__file__))))

ROOT_DIR = os.path.abspath(_ROOT_PATH)
BASE_BACKEND_DIR = os.path.join(ROOT_DIR, 'backends')
DATA_DIR = os.path.join(data_dir.get_data_dir(), 'avocado-vt')
SHARED_DIR = os.path.join(ROOT_DIR, 'shared')
DEPS_DIR = os.path.join(ROOT_DIR, 'shared', 'deps')
BASE_DOWNLOAD_DIR = os.path.join(SHARED_DIR, 'downloads')
DOWNLOAD_DIR = os.path.join(DATA_DIR, 'downloads')
TEST_PROVIDERS_DIR = os.path.join(ROOT_DIR, 'test-providers.d')
TMP_DIR = tempfile.mkdtemp()
BACKING_DATA_DIR = None


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
    return ROOT_DIR


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


def get_tmp_dir():
    return TMP_DIR


def get_download_dir():
    if not os.path.isdir(DOWNLOAD_DIR):
        shutil.copytree(BASE_DOWNLOAD_DIR, DOWNLOAD_DIR)
    return DOWNLOAD_DIR


TEST_PROVIDERS_DOWNLOAD_DIR = os.path.join(get_data_dir(), 'test-providers.d',
                                           'downloads')


def get_test_providers_dir():
    """
    Return the base test providers dir (at the moment, test-providers.d).
    """
    test_providers_dir = os.path.dirname(TEST_PROVIDERS_DOWNLOAD_DIR)
    if not os.path.isdir(test_providers_dir):
        shutil.copytree(TEST_PROVIDERS_DIR, test_providers_dir)
        os.makedirs(TEST_PROVIDERS_DOWNLOAD_DIR)
    return test_providers_dir


def get_test_provider_dir(provider):
    """
    Return a specific test providers dir, inside the base dir.
    """
    provider_dir = os.path.join(TEST_PROVIDERS_DOWNLOAD_DIR, provider)
    if not provider_dir:
        os.makedirs(provider_dir)
    return provider_dir


def clean_tmp_files():
    if os.path.isdir(TMP_DIR):
        hidden_paths = glob.glob(os.path.join(TMP_DIR, ".??*"))
        paths = glob.glob(os.path.join(TMP_DIR, "*"))
        for path in paths + hidden_paths:
            shutil.rmtree(path, ignore_errors=True)


if __name__ == '__main__':
    print "root dir:         " + ROOT_DIR
    print "tmp dir:          " + TMP_DIR
    print "data dir:         " + DATA_DIR
    print "deps dir:         " + DEPS_DIR
    print "backing data dir: " + BACKING_DATA_DIR
    print "test providers dir: " + TEST_PROVIDERS_DIR
