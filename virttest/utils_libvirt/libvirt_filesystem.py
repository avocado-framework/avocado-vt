# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
#   Copyright Red Hat
#
#   SPDX-License-Identifier: GPL-2.0
#
#   Author: smitterl@redhat.com
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
from avocado.core.exceptions import TestError


def check_idmap_xml_filesystem_device(user_info, fs_xml):
    """
    Returns whether the user idmap in the filesystem device xml
    is as expected by user_info

    :param user_info: dictionary as returned by get_user_ids
    :param fs_xml: filesystem device XML as defined by
                   libvirt_xml.devices.filesystem
    """

    if len(fs_xml.idmap.uids) + len(fs_xml.idmap.gids) != 4:
        raise TestError(
            "Expected two uid and two gid entries but got %s" % fs_xml.idmap
        )
    info_from_xml = {}
    sorted_uids = sorted(fs_xml.idmap.uids, key=lambda x: x["start"])
    info_from_xml["uid"] = int(sorted_uids[0]["target"])
    info_from_xml["subuid"] = int(sorted_uids[1]["target"])
    info_from_xml["subuid_count"] = int(sorted_uids[1]["count"])
    sorted_gids = sorted(fs_xml.idmap.gids, key=lambda x: x["start"])
    info_from_xml["gid"] = int(sorted_gids[0]["target"])
    info_from_xml["subgid"] = int(sorted_gids[1]["target"])
    info_from_xml["subgid_count"] = int(sorted_gids[1]["count"])

    for key in user_info:
        if key in ["user", "group"]:
            continue
        if user_info[key] != info_from_xml[key]:
            raise TestError(
                "The XML didn't match the expected user ids."
                " Expected: %s. Got: %s." % (user_info, info_from_xml)
            )
