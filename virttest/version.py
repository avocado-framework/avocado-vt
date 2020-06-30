#!/usr/bin/python
"""
Based on work from Douglas Creager <dcreager@dcreager.net>

Gets the current version number.  If possible, this is the
output of "git describe", modified to conform to the versioning
scheme that setuptools uses.  If "git describe" returns an error
(most likely because we're in an unpacked copy of a release tarball,
rather than in a git working copy), then we fall back on reading the
contents of the RELEASE-VERSION file.
"""
__all__ = ("get_git_version", "get_version", "get_top_commit",
           "get_current_branch", "get_pretty_version_info")

import os

from avocado.utils import process

from virttest import data_dir

_ROOT_PATH = data_dir.get_root_dir()
RELEASE_VERSION_PATH = os.path.join(_ROOT_PATH, 'RELEASE-VERSION')

global _GIT_VERSION_CACHE, _VERSION_CACHE, _TOP_COMMIT_CACHE
global _CURRENT_BRANCH_CACHE, _PRETTY_VERSION_CACHE

_GIT_VERSION_CACHE = None
_VERSION_CACHE = None
_TOP_COMMIT_CACHE = None
_CURRENT_BRANCH_CACHE = None
_PRETTY_VERSION_CACHE = None


def _execute_git_command(command):
    """
    As git is sensitive to the $CWD, change to the top dir to execute git cmds.

    :param: command - Git command to be executed.
    """
    cwd = os.getcwd()
    os.chdir(_ROOT_PATH)
    try:
        try:
            return process.run(command,
                               shell=True, verbose=False).stdout_text.strip()
        finally:
            os.chdir(cwd)
    except process.CmdError:
        return None


def get_git_version(abbrev=4):
    global _GIT_VERSION_CACHE
    if _GIT_VERSION_CACHE is not None:
        return _GIT_VERSION_CACHE

    _GIT_VERSION_CACHE = _execute_git_command('git describe --abbrev=%d' %
                                              abbrev)

    return _GIT_VERSION_CACHE


def get_top_commit():
    global _TOP_COMMIT_CACHE
    if _TOP_COMMIT_CACHE is not None:
        return _TOP_COMMIT_CACHE

    _TOP_COMMIT_CACHE = _execute_git_command(
        "git show --summary --pretty='%H' | head -1")

    return _TOP_COMMIT_CACHE


def get_current_branch():
    global _CURRENT_BRANCH_CACHE
    if _CURRENT_BRANCH_CACHE is not None:
        return _CURRENT_BRANCH_CACHE
    _CURRENT_BRANCH_CACHE = _execute_git_command('git rev-parse '
                                                 '--abbrev-ref HEAD')
    return _CURRENT_BRANCH_CACHE


def _read_release_version():
    try:
        f = open(RELEASE_VERSION_PATH, "r")
        try:
            version = f.readlines()[0]
            return version.strip()
        finally:
            f.close()
    except Exception:
        return None


def _write_release_version(version):
    try:
        f = open(RELEASE_VERSION_PATH, "w")
        f.write("%s\n" % version)
        f.close()
    except Exception:
        pass


def get_version(abbrev=4):
    global _GIT_VERSION_CACHE
    release_version = _read_release_version()
    if _GIT_VERSION_CACHE is not None:
        version = _GIT_VERSION_CACHE
    else:
        _GIT_VERSION_CACHE = get_git_version(abbrev)
        version = _GIT_VERSION_CACHE

    if version is None:
        version = release_version

    if version is None:
        try:
            cmd_result = process.run("rpm -q avocado-plugins-vt "
                                     "--queryformat '%{VERSION}'",
                                     shell=True, verbose=False)
            return '%s (RPM install)' % cmd_result.stdout_text
        except process.CmdError:
            return 'unknown'

    if version != release_version:
        _write_release_version(version)

    return version


def get_pretty_version_info():
    version_str = "Avocado-VT '%s'" % get_version()
    current_branch = get_current_branch()
    if current_branch:
        version_str += ", Branch '%s'" % current_branch
    top_commit = get_top_commit()
    if top_commit:
        version_str += ", SHA1 '%s'" % top_commit
    return version_str


if __name__ == "__main__":
    print(get_pretty_version_info())
