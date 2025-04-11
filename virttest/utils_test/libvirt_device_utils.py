import uuid

from virttest.libvirt_xml.devices.filesystem import Filesystem


def create_fs_xml(fsdev_dict, launched_mode="auto"):
    """
    Create filesystem device xml

    :param fsdev_dict: filesystem device parameter dict
    :param launched_mode: virtiofsd launched mode
    :return: filesystem device
    """
    accessmode = fsdev_dict.get("accessmode", "passthrough")
    driver = fsdev_dict.get("driver", {"type": "virtiofs"})
    source = fsdev_dict.get("source", {"dir": "/fs_share_dir"})
    target = fsdev_dict.get("target", {"dir": "fs_mount"})
    binary_dict = fsdev_dict.get("binary", {})

    fs_dev = Filesystem()
    if launched_mode == "auto":
        fs_dev.accessmode = accessmode
    fs_dev.driver = driver
    fs_dev.source = source
    fs_dev.target = target
    fs_dev.alias = {"name": "ua-" + str(uuid.uuid1())}

    if launched_mode == "auto":
        binary_xml = Filesystem.Binary()
        path = binary_dict.get("path", "/usr/libexec/virtiofsd")
        cache_mode = binary_dict.get("cache_mode", "none")
        xattr = binary_dict.get("xattr", "on")
        thread_pool_size = binary_dict.get("thread_pool_size")
        open_files_max = binary_dict.get("open_files_max")
        sandbox_mode = binary_dict.get("sandbox_mode")
        if cache_mode != "auto":
            binary_xml.cache_mode = cache_mode
        if xattr != "":
            binary_xml.xattr = xattr
        if thread_pool_size:
            binary_xml.thread_pool_size = thread_pool_size
        if open_files_max:
            binary_xml.open_files_max = open_files_max
        if sandbox_mode and sandbox_mode != "none":
            binary_xml.sandbox_mode = sandbox_mode
        binary_xml.path = path
        fs_dev.binary = binary_xml

    return fs_dev
