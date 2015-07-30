import os
import sys
import logging
import imp
import Queue
from autotest.client import test
from autotest.client.shared import error
from virttest import utils_misc, utils_params, utils_env, env_process
from virttest import data_dir, bootstrap, funcatexit, version, asset


class virt(test.test):

    """
    Shared test class infrastructure for tests such as the KVM test.

    It comprises a subtest load system, use of parameters, and an env
    file, all code that can be reused among those virt tests.
    """
    version = 1
    env_version = utils_env.get_env_version()

    def initialize(self, params):
        # Change the value of the preserve_srcdir attribute according to
        # the value present on the configuration file (defaults to yes)
        if params.get("preserve_srcdir", "yes") == "yes":
            self.preserve_srcdir = True
        virtdir = os.path.dirname(sys.modules[__name__].__file__)
        self.virtdir = os.path.join(virtdir, "shared")
        # Place where virt software will be built/linked
        self.builddir = os.path.join(virtdir, 'backends', params.get("vm_type"))
        self.background_errors = Queue.Queue()

    def verify_background_errors(self):
        """
        Verify if there are any errors that happened on background threads.

        :raise Exception: Any exception stored on the background_errors queue.
        """
        try:
            exc = self.background_errors.get(block=False)
        except Queue.Empty:
            pass
        else:
            raise exc[1], None, exc[2]

    def run_once(self, params):
        # Convert params to a Params object
        params = utils_params.Params(params)

        # If a dependency test prior to this test has failed, let's fail
        # it right away as TestNA.
        if params.get("dependency_failed") == 'yes':
            raise error.TestNAError("Test dependency failed")

        # Report virt test version
        logging.info(version.get_pretty_version_info())
        # Report the parameters we've received and write them as keyvals
        logging.debug("Test parameters:")
        keys = params.keys()
        keys.sort()
        for key in keys:
            logging.debug("    %s = %s", key, params[key])
            self.write_test_keyval({key: params[key]})

        # Set the log file dir for the logging mechanism used by kvm_subprocess
        # (this must be done before unpickling env)
        utils_misc.set_log_file_dir(self.debugdir)

        # Open the environment file
        custom_env_path = params.get("custom_env_path", "")
        if custom_env_path:
            env_path = custom_env_path
        else:
            env_path = params.get("vm_type")
        env_filename = os.path.join(self.bindir, "backends", env_path,
                                    params.get("env", "env"))
        env = utils_env.Env(env_filename, self.env_version)
        other_subtests_dirs = params.get("other_tests_dirs", "")

        test_passed = False
        t_type = None

        try:
            try:
                try:
                    subtest_dirs = []
                    bin_dir = self.bindir

                    for d in other_subtests_dirs.split():
                        # Replace split char.
                        d = os.path.join(*d.split("/"))
                        subtestdir = os.path.join(bin_dir, d, "tests")
                        if not os.path.isdir(subtestdir):
                            raise error.TestError("Directory %s not"
                                                  " exist." % (subtestdir))
                        subtest_dirs += data_dir.SubdirList(subtestdir,
                                                            bootstrap.test_filter)

                    # Verify if we have the correspondent source file for it
                    for generic_subdir in asset.get_test_provider_subdirs('generic'):
                        subtest_dirs += data_dir.SubdirList(generic_subdir,
                                                            bootstrap.test_filter)

                    for specific_subdir in asset.get_test_provider_subdirs(params.get("vm_type")):
                        subtest_dirs += data_dir.SubdirList(specific_subdir,
                                                            bootstrap.test_filter)

                    subtest_dir = None

                    # Get the test routine corresponding to the specified
                    # test type
                    logging.debug("Searching for test modules that match "
                                  "'type = %s' and 'provider = %s' "
                                  "on this cartesian dict",
                                  params.get("type"), params.get("provider", None))

                    t_types = params.get("type").split()
                    provider = params.get("provider", None)
                    if provider is not None:
                        subtest_dirs = [d for d in subtest_dirs if provider in d]
                    # Make sure we can load provider_lib in tests
                    for s in subtest_dirs:
                        if os.path.dirname(s) not in sys.path:
                            sys.path.insert(0, os.path.dirname(s))

                    test_modules = {}
                    for t_type in t_types:
                        for d in subtest_dirs:
                            module_path = os.path.join(d, "%s.py" % t_type)
                            if os.path.isfile(module_path):
                                subtest_dir = d
                                break
                        if subtest_dir is None:
                            msg = ("Could not find test file %s.py on tests"
                                   "dirs %s" % (t_type, subtest_dirs))
                            raise error.TestError(msg)
                        # Load the test module
                        f, p, d = imp.find_module(t_type, [subtest_dir])
                        test_modules[t_type] = imp.load_module(t_type, f, p, d)
                        f.close()

                    # Preprocess
                    try:
                        params = env_process.preprocess(self, params, env)
                    finally:
                        env.save()

                    # Run the test function
                    for t_type in t_types:
                        test_module = test_modules[t_type]
                        run_func = utils_misc.get_test_entrypoint_func(
                            t_type, test_module)
                        try:
                            run_func(self, params, env)
                            self.verify_background_errors()
                        finally:
                            env.save()
                    test_passed = True
                    error_message = funcatexit.run_exitfuncs(env, t_type)
                    if error_message:
                        raise error.TestWarn("funcatexit failed with: %s"
                                             % error_message)

                except Exception, e:
                    if t_type is not None:
                        error_message = funcatexit.run_exitfuncs(env, t_type)
                        if error_message:
                            logging.error(error_message)
                    logging.error("Test failed: %s: %s",
                                  e.__class__.__name__, e)
                    try:
                        env_process.postprocess_on_error(
                            self, params, env)
                    finally:
                        env.save()
                    raise

            finally:
                # Postprocess
                try:
                    try:
                        env_process.postprocess(self, params, env)
                    except Exception, e:
                        if test_passed:
                            raise
                        logging.error("Exception raised during "
                                      "postprocessing: %s", e)
                finally:
                    env.save()

        except Exception, e:
            if params.get("abort_on_error") != "yes":
                raise
            # Abort on error
            logging.info("Aborting job (%s)", e)
            if params.get("vm_type") == "qemu":
                for vm in env.get_all_vms():
                    if vm.is_dead():
                        continue
                    logging.info("VM '%s' is alive.", vm.name)
                    for m in vm.monitors:
                        logging.info(
                            "'%s' has a %s monitor unix socket at: %s",
                            vm.name, m.protocol, m.filename)
                    logging.info(
                        "The command line used to start '%s' was:\n%s",
                        vm.name, vm.make_qemu_command())
                raise error.JobError("Abort requested (%s)" % e)
