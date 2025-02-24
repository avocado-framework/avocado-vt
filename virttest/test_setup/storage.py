""" Define set/clean up procedures for storage devices
"""

import os

from avocado.utils import distro

from virttest import data_dir, test_setup
from virttest.nfs import Nfs, NFSClient
from virttest.qemu_storage import Iscsidev, LVMdev
from virttest.test_setup.core import Setuper
from virttest.utils_misc import SELinuxBoolean


class StorageConfig(Setuper):
    def setup(self):
        base_dir = data_dir.get_data_dir()
        if self.params.get("storage_type") == "iscsi":
            iscsidev = Iscsidev(self.params, base_dir, "iscsi")
            self.params["image_name"] = iscsidev.setup()
            self.params["image_raw_device"] = "yes"

        if self.params.get("storage_type") == "lvm":
            lvmdev = LVMdev(self.params, base_dir, "lvm")
            self.params["image_name"] = lvmdev.setup()
            self.params["image_raw_device"] = "yes"
            self.env.register_lvmdev("lvm_%s" % self.params["main_vm"], lvmdev)

        if self.params.get("storage_type") == "nfs":
            selinux_local = self.params.get("set_sebool_local", "yes") == "yes"
            selinux_remote = self.params.get("set_sebool_remote", "no") == "yes"
            image_nfs = Nfs(self.params)
            image_nfs.setup()
            migration_setup = self.params.get("migration_setup", "no") == "yes"
            if migration_setup:
                # Configure NFS client on remote host
                self.params["server_ip"] = self.params.get("remote_ip")
                self.params["server_user"] = self.params.get("remote_user", "root")
                self.params["server_pwd"] = self.params.get("remote_pwd")
                self.params["client_ip"] = self.params.get("local_ip")
                self.params["client_user"] = self.params.get("local_user", "root")
                self.params["client_pwd"] = self.params.get("local_pwd")
                self.params["nfs_client_ip"] = self.params.get("remote_ip")
                self.params["nfs_server_ip"] = self.params.get("local_ip")
                nfs_client = NFSClient(self.params)
                nfs_client.setup()
            distro_details = distro.detect()
            if distro_details.name.upper() != "UBUNTU":
                if selinux_local:
                    self.params["set_sebool_local"] = "yes"
                    self.params["local_boolean_varible"] = "virt_use_nfs"
                    self.params["local_boolean_value"] = self.params.get(
                        "local_boolean_value", "on"
                    )
            # configure selinux on remote host to permit migration
            if migration_setup:
                cmd = "cat /etc/os-release | grep '^PRETTY_NAME'"
                session = test_setup.remote_session(self.params)
                if "UBUNTU" not in str(session.cmd_output(cmd)).upper():
                    self.params["set_sebool_remote"] = "yes"
                    self.params["remote_boolean_varible"] = "virt_use_nfs"
                    self.params["remote_boolean_value"] = "on"
            if selinux_local or selinux_remote:
                seLinuxBool = SELinuxBoolean(self.params)
                seLinuxBool.setup()

            image_name_only = os.path.basename(self.params["image_name"])
            for image_name in self.params.objects("images"):
                name_tag = "image_name_%s" % image_name
                if self.params.get(name_tag):
                    image_name_only = os.path.basename(self.params[name_tag])
                    self.params[name_tag] = os.path.join(
                        image_nfs.mount_dir, image_name_only
                    )

    def cleanup(self):
        base_dir = data_dir.get_data_dir()
        if self.params.get("storage_type") == "iscsi":
            iscsidev = Iscsidev(self.params, base_dir, "iscsi")
            iscsidev.cleanup()

        if self.params.get("storage_type") == "lvm":
            try:
                lvmdev = self.env.get_lvmdev("lvm_%s" % self.params["main_vm"])
                lvmdev.cleanup()
            except:
                # Declare explicitly that the error will propagate
                raise
            finally:
                self.env.unregister_lvmdev("lvm_%s" % self.params["main_vm"])

        if self.params.get("storage_type") == "nfs":
            migration_setup = self.params.get("migration_setup", "no") == "yes"
            image_nfs = Nfs(self.params)
            image_nfs.cleanup()
            if migration_setup:
                # Cleanup NFS client on remote host
                nfs_client = NFSClient(self.params)
                nfs_client.cleanup(ssh_auto_recover=False)
                # Cleanup selinux on remote host
                seLinuxBool = SELinuxBoolean(self.params)
                seLinuxBool.cleanup(keep_authorized_keys=True)
