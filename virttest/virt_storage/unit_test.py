import unittest

from virttest import utils_params
from virttest.virt_storage.storage_admin import sp_admin


class VirtStorageTest(unittest.TestCase):

    def setUp(self):
        params = utils_params.Params()
        params["storage_pools"] = "sp1 sp2 sp3 sp4 sp5"
        params["storage_type_sp1"] = "directory"
        params["target_path_sp1"] = "/tmp/avocado"

        params["storage_type_sp2"] = "iscsi-direct"
        params["source_sp2"] = "s2"
        params["initiator_s2"] = "iqn.2018-01.redhat.tianxu"
        params["storage_hosts_s2"] = "h1"
        params["hostname_h1"] = '10.66.10.26'
        params["port_h1"] = '3260'
        params["devices_s2"] = "s2d1"
        params["path_s2d1"] = "iqn.2019-09.com.example:t1"
        params["authorization_s2"] = "chap"
        params["username_s2"] = "admin"
        params["password_s2"] = "password"

        params["storage_type_sp3"] = "nfs"
        params["target_path_sp3"] = "/tmp/nfs"
        params["source_sp3"] = "s3"
        params["source_dir_s3"] = "/nfs"
        params["storage_hosts_s3"] = "h3"
        params["hostname_h3"] = "127.0.0.1"

        params["storage_type_sp4"] = "rbd"
        params["source_sp4"] = "rbd"
        params["ceph_keyring_rbd"] = "AQBPxXBdAh7OJRAAC0EEml6+slcYAkZRiWN52w=="
        params["ceph_user_rbd"] = "client.admin"
        params["hosts_rbd"] = "mon1"
        params["hostname_mon1"] = "10.66.144.31"

        params["storage_type_sp5"] = "gluster"
        params["source_sp5"] = "vol"
        params["storage_hosts_vol"] = "h5"
        params["hostname_h5"] = "10.66.8.135"
        params["dir_path_gv1"] = "/"

        params["images"] = "img1 img2 img3 img4 img5 img6 img7"
        params["image_size"] = "100M"
        params["image_format"] = "raw"
        params["storage_pool_img1"] = "sp1"
        params["image_format_img1"] = "qcow2"

        params["storage_pool_img2"] = "sp2"
        params["image_format_img2"] = "raw"

        params["storage_pool_img3"] = "sp3"
        params["image_format_img3"] = "raw"
        params["image_size_img3"] = "100M"

        params["storage_pool_img4"] = "sp1"
        params["image_format_img4"] = "qcow2"
        params["image_encryption_img4"] = "luks"
        params["secret_name_img4"] = "sec0"
        params["secret_data_sec0"] = "1234"

        params["storage_pool_img5"] = "sp1"
        params["image_format_img5"] = "qcow2"
        params["image_encryption_img5"] = "on"
        params["secret_name_img5"] = "sec0"

        params["storage_pool_img6"] = "sp4"
        params["image_format_img6"] = "raw"

        params["storage_pool_img7"] = "sp5"
        params["image_format_img7"] = "qcow2"
        params["image_size_img7"] = "1G"

        params["backing_img1"] = "img4"
        params["backing_img4"] = "img5"
        self.params = params

    def test_01_pools_define_by_params(self):
        sp_admin.pools_define_by_params(self.params)
        for name in self.params.objects("storage_pools"):
            pool = sp_admin.find_pool_by_name(name)
            unittest.TestCase.assertEqual(
                self, name, pool.name, "pool name mismatch!")

    def test_02_pool_type(self):
        for pool in sp_admin.list_pools():
            expect_val = self.params.get("storage_type_%s" % pool.name)
            actual_val = pool.TYPE
            unittest.TestCase.assertEqual(
                self, expect_val, actual_val, "pool type mismatch!")

    def test_03_pool_state(self):
        for pool in sp_admin.list_pools():
            sp_admin.start_pool(pool)
            unittest.TestCase.assertEqual(
                self,
                "running",
                pool.state,
                "pool (%s) state mismatch" %
                pool.name)

    def test_04_volumes_define_by_params(self):
        sp_admin.volumes_define_by_params(self.params)
        for name in self.params.objects("images"):
            img = sp_admin.get_volume_by_name(name)
            assert img, "%s can't find by name" % name
        img1 = sp_admin.get_volume_by_name("img1")
        img4 = sp_admin.get_volume_by_name("img4")
        img5 = sp_admin.get_volume_by_name("img5")
        unittest.TestCase.assertEqual(
            self,
            img1.backing_store.name,
            img4.name,
            "img1's backing_store mismatch!")
        unittest.TestCase.assertEqual(
            self,
            img4.backing_store.name,
            img5.name,
            "img4's backing_store mismatch!")

    def test_05_acqurie_volume(self):
        for volume in sp_admin.list_volumes():
            sp_admin.acquire_volume(volume)
            unittest.TestCase.assertTrue(self, volume.is_allocated,
                                         "volume(%s) is_allocated value mismatch!" % volume.name)

    def test_06_find_pool_by_volume(self):
        for volume in sp_admin.list_volumes():
            if volume.name:
                pool = sp_admin.find_pool_by_volume(volume)
                vol_params = self.params.object_params(volume.name)
                pool_name = vol_params.get("storage_pool")
                unittest.TestCase.assertEqual(
                    self, pool.name, pool_name, "pool name mismatch!")

    def test_07_find_volume_by_key(self):
        path_img1 = "/tmp/avocado/img1"
        unittest.TestCase.assertIsNotNone(
            self,
            sp_admin.get_volume_by_name("img1"),
            "can not found img1 by name!")
        unittest.TestCase.assertIsNotNone(
            self,
            sp_admin.get_volume_by_path(path_img1),
            "can not found img1 by path!")
        unittest.TestCase.assertEqual(self, sp_admin.get_volume_by_path(path_img1),
                                      sp_admin.get_volume_by_name("img1"),
                                      "volumes are not same!")

    def test_08_find_pool_by_path(self):
        path = "/tmp/avocado"
        pool = sp_admin.find_pool_by_path(path)
        unittest.TestCase.assertEqual(
            self, "sp1", pool.name, "can not found pool by path!")

    def test_09_remove_volume(self):
        for volume in sp_admin.list_volumes():
            if volume.is_allocated:
                sp_admin.remove_volume(volume)
                unittest.TestCase.assertNotIn(self, volume, sp_admin.list_volumes(),
                                              "Volume (%s) is exists!" % volume.name)

    def test_10_stop_pool(self):
        for pool in sp_admin.list_pools():
            sp_admin.stop_pool(pool)
            unittest.TestCase.assertEqual(
                self,
                "ready",
                pool.state,
                "pool (%s) state mismatch" %
                pool.name)

    def test_11_destory_pool(self):
        for pool in sp_admin.list_pools():
            sp_admin.destroy_pool(pool)
            unittest.TestCase.assertEqual(
                self,
                "dead",
                pool.state,
                "pool (%s) state mismatch" %
                pool.name)


if __name__ == "__main__":
    loader = unittest.TestLoader()

    def ln(f): return getattr(
        VirtStorageTest,
        f).im_func.func_code.co_firstlineno

    def lncmp(a, b): return (a > b) - (a < b)

    loader.sortTestMethodsUsing = lncmp
    unittest.main(testLoader=loader, verbosity=2)
