from virttest.virt_storage.helper import glustercli, rbdcli, iscsicli, fscli, nfscli


def get_module_by_driver(driver):
    if "iscsi" in driver:
        return iscsicli
    elif driver == "gluster":
        return glustercli
    elif driver == "nfs":
        return nfscli
    elif driver == "rbd":
        return rbdcli
    elif driver == "directory":
        return fscli
    raise ValueError("unsupported driver %s" % driver)


def get_pool_helper(pool):
    driver = get_module_by_driver(pool.TYPE)
    func_name = "get_pool_helper"
    func = getattr(driver, func_name)
    return func(pool)

