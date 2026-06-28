"""

SUMMARY
------------------------------------------------------
Sample test suite tutorial pt. 2 -- *Complex test example*

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
This demo tests if certain files exist in the /etc directory of a VM
and on a second variant it extracts a tarball to the temp directory
and runs the extracted script.


INTERFACE
------------------------------------------------------

"""

import os
import subprocess
import logging

# avocado imports
from avocado.core import exceptions
try:
    from aexpect import ops_linux as ops
    OPS_AVAILABLE = True
except ImportError:
    log.warning("The session ops of an upgraded aexpect package are not available")
    OPS_AVAILABLE = False

# custom imports
from sample_utility import sleep


log = logging.getLogger('avocado.test.log')


###############################################################################
# CONSTANTS
###############################################################################


TARBALL_DESTINATION = "/tmp"


###############################################################################
# HELPER FUNCTIONS
###############################################################################


def extract_tarball(params, vm):
    """
    Here we extract our tarball with the file we want to run, checking
    if the file hash matches before proceeding. Note that the extraction
    is done on the guest VM, remotely from the host.

    In this test suite, whatever is located in the data directory
    of a test (tp_folder/data/<$TEST_NAME>) will be pushed to the path
    /tmp/data/<$TEST_NAME> on the VM.
    This can be adapted using the parameter `deployed_test_data_path`.

    This function is run for each test run, i.e. for each call to
    run() below.

    :param params: extended dictionary of parameters
    :type params: {str, str}
    :params vm: used guest VM
    :type vm: :py:class:`virttest.qemu_vm.VM`
    """
    log.info("Enter tutorial test variant one: extract and run a file.")
    tarball_path = os.path.join(
        params["deployed_test_data_path"],
        "tutorial_step_2",
        "check_names.tar.gz"
    )

    # One way to execute commands remotely on the guest VM is to
    # use the methods from the `session` object. Here we invoke
    # a shell command and capture its output.
    hash_out = vm.session.cmd_output("md5sum %s" % tarball_path)

    # A sanity check just in case (use entire hash output to deal with CentOS locale problems)
    if params["md5sum"] not in hash_out:
        raise exceptions.TestError("MD5 checksum mismatch of file %s: "
                                   "expected %s, got:\n%s"
                                   % (tarball_path, params["md5sum"], hash_out))

    vm.session.cmd("tar -xf %s -C %s" % (tarball_path, TARBALL_DESTINATION))


def run_extracted_script(params, vm):
    """
    Verify that the script from the tarball has been successfully extracted
    and run it, checking its return code.

    :param params: extended dictionary of parameters
    :type params: {str, str}
    :params vm: used guest VM
    :type vm: :py:class:`virttest.qemu_vm.VM`
    """
    scriptdir = params["script"]
    scriptname = scriptdir + ".sh"
    scriptabspath = os.path.join(
        TARBALL_DESTINATION,
        scriptdir,
        scriptname
    )

    # The easiest and most universal way to run a command on a vm is using its
    # session (usually one but more available after additional logins)
    vm.session.cmd("test -f " + scriptabspath)
    if OPS_AVAILABLE:
        # We can also use the `linux_ops` module, which contains some IO functions
        # to be executed on a guest VM. This can be considered another way to remotely
        # run operations on a guest.
        if not ops.is_regular_file(vm.session, scriptabspath):
            raise exceptions.TestError("Expected file %s to have been extracted, "
                                       "but it doesn't exist." % scriptabspath)
        else:
            log.info("The extracted script was also verified through session ops")

    vm.session.cmd(scriptabspath + " " + vm.name)


def check_files(params, vm):
    """
    Asserts that some files exist on the guest VM and some others
    don't. Those files are provided by the Cartesian configuration
    and can be customized there.

    :param params: extended dictionary of parameters
    :type params: {str, str}
    :params vm: used guest VM
    :type vm: :py:class:`virttest.qemu_vm.VM`
    """
    log.info("Enter tutorial test variant two: check files.")

    must_exist = params["must_exist"].split(" ")
    must_not_exist = params["must_not_exist"].split(" ")
    files_prefix = params["files_prefix"]

    def aux(f):
        """Construct absolute path to file and test presence in fs verbosely."""
        fullpath = os.path.join(files_prefix, f)
        result = vm.session.cmd_status("! test -f " + fullpath)
        # alternatively, use more python interface through session ops
        if OPS_AVAILABLE:
            result2 = ops.is_regular_file(vm.session, fullpath)
            assert result == result2
        log.info(f"  - Verifying the presence of file {fullpath} -> "
                 f"{result and 'exists' or 'nil'}.")
        return result

    missing = [f for f in must_exist if not aux(f)]
    unwanted = [f for f in must_not_exist if aux(f)]

    if missing and unwanted:
        log.info("Unluckily, we encountered both unwanted and missing files.")
        raise exceptions.TestFail(
            "%d mandatory files not found in path %s: \"%s\";\n"
            "%d unwanted files in path %s: \"%s\"."
            % (len(missing), files_prefix, ", ".join(missing),
               len(unwanted), files_prefix, ", ".join(unwanted)))
    elif missing:
        log.info("Unluckily, some required files were missing.")
        raise exceptions.TestFail("%d mandatory files not found in path %s: \"%s\"."
                                  % (files_prefix, len(missing), ", ".join(missing)))
    elif unwanted:
        log.info("Unluckily, we tripped over files we really struggled to avoid.")
        raise exceptions.TestFail("%d unwanted files in path %s: \"%s\"."
                                  % (files_prefix, len(unwanted), ", ".join(unwanted)))


###############################################################################
# TEST MAIN
###############################################################################


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
    vm, _ = vmnet.get_single_vm_with_session()

    # call to a function shared among tests
    sleep(3)

    # We use the check_kind parameter from the Cartesian configuration
    # to decide which test to run
    if params["check_kind"] == "names":
        vm.copy_files_to(
            os.path.join(params["original_test_data_path"], "tutorial_step_2"),
            params["deployed_test_data_path"],
        )
        extract_tarball(params, vm)
        run_extracted_script(params, vm)
    else:
        check_files(params, vm)
