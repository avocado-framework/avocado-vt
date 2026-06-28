"""

SUMMARY
------------------------------------------------------
Deploy guest tests, utilities and data to the main virtual machine.

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
If the vm is linux-based add some conveniences like ssh key or extra rpms.
If the vm is windows-based add some GUI-tweaks like resolution and welcome messages.


INTERFACE
------------------------------------------------------

"""

import tempfile
import os
import logging
import sys

# avocado imports
from avocado.core import exceptions
from avocado.core.settings import settings
from virttest import error_context

# custom imports
pass


log = logging.getLogger('avocado.test.log')


###############################################################################
# DEFINITIONS
###############################################################################


source_avocado_path = f"/usr/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages/avocado/utils"
destination_avocado_path = "/tmp/utils/avocado"


###############################################################################
# HELPERS
###############################################################################


def deploy_avocado(vm):
    """
    Deploy the avocado package to a vm.

    :param vm: vm to deploy to (must be compatible)
    :type vm: :py:class:`virttest.qemu_vm.VM`
    """
    # TODO: scp does not seem to raise exception if path does not exist
    log.info(f"Deploying avocado utilities at {vm.params['main_vm']}")
    log.debug(f"Deploying utilities from {source_avocado_path} on host to "
              f"{destination_avocado_path} on the virtual machine.")
    vm.session.cmd("mkdir -p " + destination_avocado_path)
    vm.session.cmd("touch " + os.path.join(destination_avocado_path, "__init__.py"))
    vm.copy_files_to(source_avocado_path, destination_avocado_path, timeout=180)


def deploy_data(vm, folder_name, dst_folder_name="", custom_src_path="", timeout=60):
    """
    Deploy data to a vm.

    :param vm: vm to deploy to (must be compatible)
    :type vm: :py:class:`virttest.qemu_vm.VM`
    :param str folder_name: data folder name (default path is 'guest')
    :param params: deploy configuration
    :type params: {str, str}
    :param str custom_src_path: custom path to the src data folder
    :param str custom_dst_name: custom folder name of the dst data folder
    :param int timeout: copying timeout
    """
    if custom_src_path == "":
        src_path = os.path.join(vm.params["suite_path"], folder_name)
    else:
        src_path = os.path.join(custom_src_path, folder_name)
    tmp_dir = vm.params.get("tmp_dir", "/tmp")
    folder_name = dst_folder_name if dst_folder_name else folder_name
    dst_path = os.path.join(tmp_dir, folder_name)
    cmd = f"rm -fr" if vm.params.get("os_type", "linux") == "linux" else "rmdir /s /q"
    cmd += f" {dst_path}"
    vm.session.cmd(cmd)
    vm.copy_files_to(src_path, dst_path, timeout=timeout)


def handle_ssh_authorized_keys(vm):
    """
    Deploy an SSH key to a vm.

    :param vm: vm to deploy to (must be compatible)
    :type vm: :py:class:`virttest.qemu_vm.VM`
    """
    ssh_authorized_keys = os.environ['SSHKEY'] if 'SSHKEY' in os.environ else ""
    if ssh_authorized_keys == "":
        return
    log.info(f"Enabled ssh key '{ssh_authorized_keys}'")

    tmpfile = tempfile.NamedTemporaryFile(delete=False)
    tmpfile.write((ssh_authorized_keys + '\n').encode())
    tmpfile.close()

    vm.session.cmd('mkdir -p /root/.ssh')
    vm.copy_files_to(tmpfile.name, '/root/.ssh/authorized_keys')
    os.unlink(tmpfile.name)


###############################################################################
# TEST MAIN
###############################################################################


@error_context.context_aware
def run(test, params, env):
    """
    Main test run.

    :param test: test object
    :type test: :py:class:`avocado_vt.test.VirtTest`
    :param params: extended dictionary of parameters
    :type params: :py:class:`virttest.utils_params.Params`
    :param env: environment object
    :type env: :py:class:`virttest.utils_env.Env`
    """
    vmnet = env.get_vmnet()
    vm, session, params = vmnet.get_single_vm_with_session_and_params()
    os_type = params.get("os_type", "linux")
    os_variant = params.get("os_variant", "fedora")
    tmp_dir = params.get("tmp_dir", "/tmp")

    # main deployment part
    # WARNING: control file must add path to utils to the pythonpath
    log.info(f"Deploying customized test utilities to {tmp_dir} on {params['main_vm']}")
    deploy_data(vm, "utils/")
    # as avocado utils are deployed in a subdirectory, deploy them after the general utils
    if params.get_boolean("guest_avocado_enabled"):
        if os.path.exists(source_avocado_path):
            deploy_avocado(vm)
        else:
            raise exceptions.TestFail(
                "No source avocado path found and could be deployed"
            )

    # additional deployment part
    additional_deployment_path = params.get("additional_deployment_dir", "/mnt/local/packages")
    destination_packages_path = params.get("deployed_packages_path", "/tmp/packages")
    if additional_deployment_path is not None and os.path.isdir(additional_deployment_path):
        log.info(f"Deploying additional packages and data to {tmp_dir} on {params['main_vm']}")
        # careful about the splitting process - since we perform deleting need to validate here
        additional_deployment_path = additional_deployment_path.rstrip("/")
        deploy_data(vm, os.path.basename(additional_deployment_path), "packages",
                    os.path.dirname(additional_deployment_path), 60)
    else:
        raise exceptions.TestError("Additional deployment path %s does not exist (current dir: "
                                   "%s)" % (additional_deployment_path, os.getcwd()))
    if params.get("extra_rpms", None) is not None:
        if os_type != "linux":
            raise NotImplementedError("RPM updates are only available on some linux distros and not %s" % os_type)
        for rpm in params.objects("extra_rpms"):
            session.cmd("rpm -Uv --force %s" % os.path.join(destination_packages_path, rpm))
            log.info(f"Updated package: {rpm}")

    if os_type == "linux" and params.get("redeploy_only", "no") == "no":
        handle_ssh_authorized_keys(vm)

    log.info("Customized tests setup on VM finished")
    session.close()
