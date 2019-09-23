import pprint

from virttest import utils_params
from virttest.storage.storage_pool import storage_pool_factory 
from virttest.storage.storage_volume import storage_volume_factory

sp_manager = storage_pool_factory.StoragePoolFactory()
vol_manager = storage_volume_factory.StorageVolumeFactory() 

def build_storage_pool(sp_name, sp_params):
    sp_type = sp_params["storage_type"]
    return sp_manager.produce(sp_name, sp_type, sp_params)


def build_stroage_pools(test_params):
    """Build storage pool object in batch mode"""
    pools = list()
    for sp_name in test_params.objects("storage_pools"):
        sp_params = test_params.object_params(sp_name)
        pool = sp_manager.get_pool_by_name(sp_name)
        if not pool:
            pool = build_storage_pool(sp_name, sp_params)
        pools.append(pool)
    return pools

if __name__ == "__main__":
    params = utils_params.Params()
    params["storage_pools"] = "sp1 sp2 sp3"
    params["storage_type_sp1"] = "file"
    params["storage_type_sp2"] = "iscsi"
    params["storage_type_sp3"] = "nfs"

    params["path"] = "/tmp/a"
    params["path_sp1"] = "/tmp/a"

    params["iscsi_host_sp2"] = "10.66.10.26"
    params["iscsi_port_sp2"] = "3260"
    params["iscsi_initiator_sp2"] = "iqn.2018-01.redhat.kvm-autotest"
    params["iscsi_target_sp2"] = "iqn.2019-09.com.example:zhencliu"

    params["nfs_dir_sp3"] = "/nfs"
    params["nfs_host_sp3"] = "127.0.0.1"

    params["images"] = "img1 img2 img3 img4"

    params["storage_pool_img1"] = "sp1"
    params["storage_pool_img2"] = "sp2"
    params["storage_pool_img3"] = "sp3"
    params["storage_pool_img4"] = "sp1"

    params["image_format_img1"] = "qcow2"
    params["image_format_img2"] = "luks"
    params["image_format_img3"] = "raw"
    params["image_format_imgt"] = "raw"

    params["image_filename_img1"] = "/tmp/a.qcow2"
    params["image_filename_img4"] = "/tmp/b.qcow2"
    params["nfs_image_name_img3"] = "img3_nfs"


    params["backing_img1"] = "img4"

    pools = build_stroage_pools(params)
    map(sp_manager.create_storage_pool, pools)
    for name in params.objects("images"):
        volume = vol_manager.factory(name, params)
         
    
    img1 = sp_manager.get_volume_by_name("sp1", "img1")
    assert img1.backing.name == "img4"
    
    pprint.pprint(vars(img1.protocol))
    pprint.pprint(vars(img1.fmt))

    img2 = sp_manager.get_volume_by_name("sp2", "img2")
    assert img2.backing == None

    img3 = sp_manager.get_volume_by_name("sp3", "img3")
    img3.backing  == None
