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


def get_instance_info(inst):
    _info = dict()
    for key, val in vars(inst).items():
        # skip method
        if callable(val):
            continue
        # skip private attributes
        if key.startswith("_"):
            key = key.lstrip("_")
            if hasattr(inst, key):
                _info[key] = getattr(inst, key)
            continue

        if isinstance(val, list):
            val = list(map(str, val))
            _info[key] = val
            continue
        elif isinstance(val, dict):
            for k, v in val.items():
                val[k] = str(v)
            _info[key] = val
            continue
        else:
            _info[key] = str(val)
            continue
    return _info
