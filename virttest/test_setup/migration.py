from virttest import migration, test_setup, utils_net
from virttest._wrappers import lazy_import
from virttest.test_setup.core import Setuper
from virttest.utils_conn import SSHConnection

libvirt_vm = lazy_import("virttest.libvirt_vm")
virsh = lazy_import("virttest.virsh")


class MigrationEnvSetup(Setuper):
    def setup(self):
        if self.params.get("migration_setup", "no") == "yes":
            # Permit iptables to permit 49152-49216 ports to libvirt for
            # migration and if arch is ppc with power8 then switch off smt
            # will be taken care in remote machine for migration to succeed
            dest_uri = libvirt_vm.complete_uri(
                self.params.get("server_ip", self.params.get("remote_ip"))
            )
            migrate_setup = migration.MigrationTest()
            migrate_setup.migrate_pre_setup(dest_uri, self.params)
            # Map hostname and IP address of the hosts to avoid virsh
            # to error out of resolving
            hostname_ip = {str(virsh.hostname()): self.params["local_ip"]}
            session = test_setup.remote_session(self.params)
            _, remote_hostname = session.cmd_status_output("hostname")
            hostname_ip[str(remote_hostname.strip())] = self.params["remote_ip"]
            if not utils_net.map_hostname_ipaddress(hostname_ip):
                self.test.cancel("Failed to map hostname and ipaddress of source host")
            if not utils_net.map_hostname_ipaddress(hostname_ip, session=session):
                session.close()
                self.test.cancel("Failed to map hostname and ipaddress of target host")
            session.close()
            if self.params.get("setup_ssh") == "yes":
                ssh_conn_obj = SSHConnection(self.params)
                ssh_conn_obj.conn_setup()
                ssh_conn_obj.auto_recover = True
                self.params.update({"ssh_conn_obj": ssh_conn_obj})

    def cleanup(self):
        # cleanup migration presetup in post process
        if self.params.get("migration_setup", "no") == "yes":
            dest_uri = libvirt_vm.complete_uri(
                self.params.get("server_ip", self.params.get("remote_ip"))
            )
            migrate_setup = migration.MigrationTest()
            migrate_setup.migrate_pre_setup(dest_uri, self.params, cleanup=True)
            if self.params.get("setup_ssh") == "yes" and self.params.get(
                "ssh_conn_obj"
            ):
                del self.params["ssh_conn_obj"]
