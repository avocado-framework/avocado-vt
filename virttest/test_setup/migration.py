import logging

from avocado.utils import cpu as cpu_utils
from avocado.utils import process as a_process

from virttest import migration, test_setup, utils_net
from virttest._wrappers import lazy_import
from virttest.test_setup.core import Setuper
from virttest.utils_conn import SSHConnection

libvirt_vm = lazy_import("virttest.libvirt_vm")
virsh = lazy_import("virttest.virsh")

LOG = logging.getLogger(__name__)


class MigrationEnvSetup(Setuper):
    def setup(self):
        if self.params.get("migration_setup", "no") == "yes":
            # For KVM to work in Power8 and Power9(compat guests)(<DD2.2)
            # systems we need to have SMT=off and it needs to be
            # done as root, here we do a check whether
            # we satisfy that condition, if not try to make it off
            # otherwise throw TestError with respective error message
            cpu_family = "unknown"
            try:
                cpu_family = (
                    cpu_utils.get_family()
                    if hasattr(cpu_utils, "get_family")
                    else cpu_utils.get_cpu_arch()
                )
            except Exception:
                LOG.warning("Could not get host cpu family")
            if cpu_family is not None and "power" in str(cpu_family):
                pvr_cmd = "grep revision /proc/cpuinfo | awk '{print $3}' | head -n 1"
                pvr = float(a_process.system_output(pvr_cmd, shell=True).strip())
                power9_compat_remote = "yes" == self.params.get(
                    "power9_compat_remote", "no"
                )
                cpu_cmd = "grep cpu /proc/cpuinfo | awk '{print $3}' | head -n 1"
                remote_host = {
                    "server_ip": self.params.get("remote_ip"),
                    "server_pwd": self.params.get("remote_pwd"),
                    "server_user": self.params.get("remote_user", "root"),
                }
                server_session = test_setup.remote_session(remote_host)
                cmd_output = server_session.cmd_status_output(cpu_cmd)
                if cmd_output[0] == 0:
                    remote_cpu = cmd_output[1].strip().lower()
                cmd_output = server_session.cmd_status_output(pvr_cmd)
                if cmd_output[0] == 0:
                    remote_pvr = float(cmd_output[1].strip())
                server_session.close()
                if "power8" in remote_cpu:
                    test_setup.switch_smt(state="off", params=self.params)
                elif (
                    "power9" in remote_cpu and power9_compat_remote and remote_pvr < 2.2
                ):
                    test_setup.switch_indep_threads_mode(state="N", params=self.params)
                    test_setup.switch_smt(state="off", params=self.params)
                if pvr != remote_pvr:
                    LOG.warning(
                        "Source and destinations system PVR "
                        "does not match\n PVR:\nSource: %s"
                        "\nDestination: %s",
                        pvr,
                        remote_pvr,
                    )

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
            cpu_family = "unknown"
            try:
                cpu_family = (
                    cpu_utils.get_family()
                    if hasattr(cpu_utils, "get_family")
                    else cpu_utils.get_cpu_arch()
                )
            except Exception:
                LOG.warning("Could not get host cpu family")
            if cpu_family is not None and "power" in str(cpu_family):
                pvr_cmd = "grep revision /proc/cpuinfo | awk '{print $3}' | head -n 1"
                power9_compat_remote = (
                    self.params.get("power9_compat_remote", "no") == "yes"
                )
                cpu_cmd = "grep cpu /proc/cpuinfo | awk '{print $3}' | head -n 1"
                server_session = test_setup.remote_session(self.params)
                cmd_output = server_session.cmd_status_output(cpu_cmd)
                if cmd_output[0] == 0:
                    remote_cpu = cmd_output[1].strip().lower()
                cmd_output = server_session.cmd_status_output(pvr_cmd)
                if cmd_output[0] == 0:
                    remote_pvr = float(cmd_output[1].strip())
                server_session.close()
                if (
                    ("power9" in remote_cpu)
                    and power9_compat_remote
                    and remote_pvr < 2.2
                ):
                    test_setup.switch_indep_threads_mode(state="Y", params=self.params)
                    test_setup.switch_smt(state="on", params=self.params)

            dest_uri = libvirt_vm.complete_uri(
                self.params.get("server_ip", self.params.get("remote_ip"))
            )
            migrate_setup = migration.MigrationTest()
            migrate_setup.migrate_pre_setup(dest_uri, self.params, cleanup=True)
            if self.params.get("setup_ssh") == "yes" and self.params.get(
                "ssh_conn_obj"
            ):
                del self.params["ssh_conn_obj"]
