# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
#   Copyright Red Hat
#
#   SPDX-License-Identifier: GPL-2.0
#
#   Author: smitterl@redhat.com
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
import grp
import pwd

from avocado.core.exceptions import TestError
from avocado.utils import process


def get_user_ids(user):
    """
    Returns user uid, gid and their respective subuids and subgids
    along with their names as a dictionary:

    {
        "user": username
        "group": groupname
        "uid" : 116284,
        "subuid": 165536,
        "subuid_count": 165536,
        "gid": 116284,
        "subgid": 165536,
        "subgid_count": 165536
    }

    :param user: username
    """

    info = {}

    _get_uid_gid(user, info)
    _get_subid("/etc/subuid", info["user"], info)
    _get_subid("/etc/subgid", info["group"], info)

    return info


def _get_subid(id_filepath, name, info):
    """
    Reads sub id info from disk and stores it in 'info'

    :param id_filepath: which file to read the info for
                        the file is expected to contain lines
                        "name:numerical subordinate ID:numerical subordinate ID count"
    :param name: a name that identifies the line to scan values for
    :param info: dictionary to store the values
    """

    result = process.run("cat %s" % id_filepath, ignore_status=True)
    if result.exit_status:
        raise TestError("Couldn't read %s" % id_filepath)

    entry = [
        l
        for l in result.stdout_text.split("\n")
        if name in l and name == l.split(":")[0]
    ]
    if not entry:
        raise TestError("No entry for %s found in %s" % (name, id_filepath))

    entry = entry[0].split(":")

    key1, key2 = "subuid", "subuid_count"
    if "subgid" in id_filepath:
        key1, key2 = "subgid", "subgid_count"

    info[key1] = int(entry[1])
    info[key2] = int(entry[2])


def _get_uid_gid(user, info):
    """
    Fills the parameter dictionary 'info' with 'uid' and 'gid'
    of the given user

    :param user: username
    :param info: dictionary to store return values
    """

    u_info = pwd.getpwnam(user)
    g_info = grp.getgrgid(u_info.pw_gid)

    info["user"] = user
    info["group"] = g_info.gr_name
    info["uid"] = u_info.pw_uid
    info["gid"] = u_info.pw_gid
