"""
Windows system utilities
"""

from . import wmic


def _osinfo(session, props=None):
    cmd = wmic.make_query("os", props=props, get_swch=wmic.FMT_TYPE_LIST)
    try:
        return wmic.parse_list(session.cmd(cmd))[0]
    except IndexError:
        return None


def product_name(session):
    """
    Get Windows product name.

    :param session: Session object.

    :return: Windows product name.
    """
    return _osinfo(session, props=["Caption"])


def version(session):
    """
    Get Windows version.

    :param session: Session object.

    :return: Windows version.
    """
    return _osinfo(session, props=["Version"])


def os_arch(session):
    """
    Get Windows OS architecture.

    :param session: Session object.

    :return: Windows OS architecture.
    """
    return _osinfo(session, props=["OSArchitecture"])
