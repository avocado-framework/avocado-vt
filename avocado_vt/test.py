# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2015
# Author: Lucas Meneghel Rodrigues <lmr@redhat.com>

"""
Avocado VT plugin
"""

import imp
import logging
import os
import Queue
import sys

from avocado.core import exceptions
from avocado.core import test
from avocado.utils import genio
from avocado.utils import stacktrace

from virttest import asset
from virttest import bootstrap
from virttest import data_dir
from virttest import env_process
from virttest import funcatexit
from virttest import utils_env
from virttest import utils_params
from virttest import utils_misc
from virttest import version

# avocado-vt no longer needs autotest for the majority of its functionality,
# except by:
# 1) Run autotest on VMs
# 2) Multi host migration
# 3) Proper avocado-vt test status handling
# As in those cases we might want to use autotest, let's have a way for
# users to specify their autotest from a git clone location.
AUTOTEST_PATH = None

if 'AUTOTEST_PATH' in os.environ:
    AUTOTEST_PATH = os.path.expanduser(os.environ['AUTOTEST_PATH'])
    CLIENT_DIR = os.path.join(os.path.abspath(AUTOTEST_PATH), 'client')
    SETUP_MODULES_PATH = os.path.join(CLIENT_DIR, 'setup_modules.py')
    if not os.path.exists(SETUP_MODULES_PATH):
        raise EnvironmentError("Although AUTOTEST_PATH has been declared, "
                               "%s missing." % SETUP_MODULES_PATH)
    SETUP_MODULES = imp.load_source('autotest_setup_modules',
                                    SETUP_MODULES_PATH)
    SETUP_MODULES.setup(base_path=CLIENT_DIR,
                        root_module_name="autotest.client")

from autotest.client.shared import error


def cleanup_env(env_filename, env_version):
    """
    Pickable function to initialize and destroy the virttest env
    """
    env = utils_env.Env(env_filename, env_version)
    env.destroy()


class VirtTest(test.Test):

    """
    Mininal test class used to run a virt test.
    """

    env_version = utils_env.get_env_version()

    def __init__(self, methodName='runTest', name=None, params=None,
                 base_logdir=None, job=None, runner_queue=None,
                 vt_params=None):
        """
        :note: methodName, name, base_logdir, job and runner_queue params
               are inherited from test.Test
        :param params: avocado/multiplexer params stored as
                       `self.avocado_params`.
        :param vt_params: avocado-vt/cartesian_config params stored as
                          `self.params`.
        """
        self.bindir = data_dir.get_root_dir()
        self.virtdir = os.path.join(self.bindir, 'shared')

        self.iteration = 0
        self.resultsdir = None
        self.file_handler = None
        self.background_errors = Queue.Queue()
        super(VirtTest, self).__init__(methodName=methodName, name=name,
                                       params=params,
                                       base_logdir=base_logdir, job=job,
                                       runner_queue=runner_queue)
        self.builddir = os.path.join(self.workdir, 'backends',
                                     vt_params.get("vm_type"))
        self.tmpdir = os.path.dirname(self.workdir)
        # Move self.params to self.avocado_params and initialize virttest
        # (cartesian_config) params
        self.avocado_params = self.params
        self.params = utils_params.Params(vt_params)
        self.debugdir = self.logdir
        self.resultsdir = self.logdir
        self.timeout = vt_params.get("test_timeout", self.timeout)
        utils_misc.set_log_file_dir(self.logdir)

    @property
    def datadir(self):
        """
        Returns the path to the directory that contains test data files

        For VT tests, this always returns None. The reason is that
        individual VT tests do not map 1:1 to a file and do not provide
        the concept of a datadir.
        """
        return None

    @property
    def filename(self):
        """
        Returns the name of the file (path) that holds the current test

        For VT tests, this always returns None. The reason is that
        individual VT tests do not map 1:1 to a file.
        """
        return None

    def get_state(self):
        """
        Avocado-vt replaces Test.params with avocado-vt params. This function
        reports the original params on `get_state` call.
        """
        state = super(VirtTest, self).get_state()
        state["params"] = self.__dict__.get("avocado_params")
        return state

    def _start_logging(self):
        super(VirtTest, self)._start_logging()
        root_logger = logging.getLogger()
        root_logger.addHandler(self.file_handler)

    def _stop_logging(self):
        super(VirtTest, self)._stop_logging()
        root_logger = logging.getLogger()
        root_logger.removeHandler(self.file_handler)

    def write_test_keyval(self, d):
        self.whiteboard = str(d)

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

    def __safe_env_save(self, env):
        """
        Treat "env.save()" exception as warnings

        :param env: The virttest env object
        :return: True on failure
        """
        try:
            env.save()
        except Exception as details:
            if hasattr(stacktrace, "str_unpickable_object"):
                self.log.warn("Unable to save environment: %s",
                              stacktrace.str_unpickable_object(env.data))
            else:    # TODO: Remove when 36.0 LTS is not supported
                self.log.warn("Unable to save environment: %s (%s)", details,
                              env.data)
            return True
        return False

    def runTest(self):
        env_lang = os.environ.get('LANG')
        os.environ['LANG'] = 'C'
        try:
            self._runTest()
        # This trick will give better reporting of virt tests being executed
        # into avocado (skips, warns and errors will display correctly)
        except error.TestNAError, details:
            raise exceptions.TestSkipError(details)
        except error.TestWarn, details:
            raise exceptions.TestWarn(details)
        except error.TestError, details:
            raise exceptions.TestError(details)
        except error.TestFail, details:
            raise exceptions.TestFail(details)
        finally:
            if env_lang:
                os.environ['LANG'] = env_lang
            else:
                del os.environ['LANG']

    def _runTest(self):
        params = self.params

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

        # Warn of this special condition in related location in output & logs
        if os.getuid() == 0 and params.get('nettype', 'user') == 'user':
            logging.warning("")
            logging.warning("Testing with nettype='user' while running "
                            "as root may produce unexpected results!!!")
            logging.warning("")

        # Find the test
        subtest_dirs = []
        test_filter = bootstrap.test_filter

        other_subtests_dirs = params.get("other_tests_dirs", "")
        for d in other_subtests_dirs.split():
            d = os.path.join(*d.split("/"))
            subtestdir = os.path.join(self.bindir, d, "tests")
            if not os.path.isdir(subtestdir):
                raise error.TestError("Directory %s does not "
                                      "exist" % subtestdir)
            subtest_dirs += data_dir.SubdirList(subtestdir,
                                                test_filter)

        provider = params.get("provider", None)

        if provider is None:
            # Verify if we have the correspondent source file for
            # it
            generic_subdirs = asset.get_test_provider_subdirs(
                'generic')
            for generic_subdir in generic_subdirs:
                subtest_dirs += data_dir.SubdirList(generic_subdir,
                                                    test_filter)
            specific_subdirs = asset.get_test_provider_subdirs(
                params.get("vm_type"))
            for specific_subdir in specific_subdirs:
                subtest_dirs += data_dir.SubdirList(
                    specific_subdir, bootstrap.test_filter)
        else:
            provider_info = asset.get_test_provider_info(provider)
            for key in provider_info['backends']:
                subtest_dirs += data_dir.SubdirList(
                    provider_info['backends'][key]['path'],
                    bootstrap.test_filter)

        subtest_dir = None

        # Get the test routine corresponding to the specified
        # test type
        logging.debug("Searching for test modules that match "
                      "'type = %s' and 'provider = %s' "
                      "on this cartesian dict",
                      params.get("type"),
                      params.get("provider", None))

        t_types = params.get("type").split()
        # Make sure we can load provider_lib in tests
        for s in subtest_dirs:
            if os.path.dirname(s) not in sys.path:
                sys.path.insert(0, os.path.dirname(s))

        test_modules = {}
        for t_type in t_types:
            for d in subtest_dirs:
                module_path = os.path.join(d, "%s.py" % t_type)
                if os.path.isfile(module_path):
                    logging.debug("Found subtest module %s",
                                  module_path)
                    subtest_dir = d
                    break
            if subtest_dir is None:
                msg = ("Could not find test file %s.py on test"
                       "dirs %s" % (t_type, subtest_dirs))
                raise error.TestError(msg)
            # Load the test module
            f, p, d = imp.find_module(t_type, [subtest_dir])
            test_modules[t_type] = imp.load_module(t_type, f, p, d)
            f.close()

        # TODO: the environment file is deprecated code, and should be removed
        # in future versions. Right now, it's being created on an Avocado temp
        # dir that is only persisted during the runtime of one job, which is
        # different from the original idea of the environment file (which was
        # persist information accross virt-test/avocado-vt job runs)
        env_filename = os.path.join(data_dir.get_tmp_dir(),
                                    params.get("env", "env"))
        env = utils_env.Env(env_filename, self.env_version)
        self.runner_queue.put({"func_at_exit": cleanup_env,
                               "args": (env_filename, self.env_version),
                               "once": True})

        test_passed = False
        t_type = None

        try:
            try:
                try:
                    # Preprocess
                    try:
                        params = env_process.preprocess(self, params, env)
                    finally:
                        self.__safe_env_save(env)

                    # Run the test function
                    for t_type in t_types:
                        test_module = test_modules[t_type]
                        run_func = utils_misc.get_test_entrypoint_func(
                            t_type, test_module)
                        try:
                            run_func(self, params, env)
                            self.verify_background_errors()
                        finally:
                            self.__safe_env_save(env)
                    test_passed = True
                    error_message = funcatexit.run_exitfuncs(env, t_type)
                    if error_message:
                        raise error.TestWarn("funcatexit failed with: %s" %
                                             error_message)

                except Exception:
                    if t_type is not None:
                        error_message = funcatexit.run_exitfuncs(env, t_type)
                        if error_message:
                            logging.error(error_message)
                    try:
                        env_process.postprocess_on_error(self, params, env)
                    finally:
                        self.__safe_env_save(env)
                    raise

            finally:
                # Postprocess
                try:
                    try:
                        params['test_passed'] = str(test_passed)
                        env_process.postprocess(self, params, env)
                    except Exception, e:
                        if test_passed:
                            raise
                        logging.error("Exception raised during "
                                      "postprocessing: %s", e)
                finally:
                    if self.__safe_env_save(env):
                        env.destroy()   # Force-clean as it can't be stored

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
                        logging.info("It has a %s monitor unix socket at: %s",
                                     m.protocol, m.filename)
                    logging.info("The command line used to start it was:\n%s",
                                 vm.make_create_command())
                raise error.JobError("Abort requested (%s)" % e)

        return test_passed

    def _run_avocado(self):
        """
        Auxiliary method to run_avocado.

        We have to override this method because the avocado-vt plugin
        has to override the behavior that tests shouldn't raise
        exceptions.TestSkipError by themselves in avocado. In the old
        avocado-vt case, that rule is not in place, so we have to be
        a little more lenient for correct test status reporting.
        """
        testMethod = getattr(self, self._testMethodName)
        self._start_logging()
        self.sysinfo_logger.start_test_hook()
        test_exception = None
        cleanup_exception = None
        stdout_check_exception = None
        stderr_check_exception = None
        try:
            self.setUp()
        except exceptions.TestSkipError, details:
            stacktrace.log_exc_info(sys.exc_info(), logger='avocado.test')
            raise exceptions.TestSkipError(details)
        except Exception, details:
            stacktrace.log_exc_info(sys.exc_info(), logger='avocado.test')
            raise exceptions.TestSetupFail(details)
        try:
            testMethod()
        except Exception, details:
            stacktrace.log_exc_info(sys.exc_info(), logger='avocado.test')
            test_exception = details
        finally:
            try:
                self.tearDown()
            except Exception, details:
                stacktrace.log_exc_info(sys.exc_info(), logger='avocado.test')
                cleanup_exception = details

        whiteboard_file = os.path.join(self.logdir, 'whiteboard')
        genio.write_file(whiteboard_file, self.whiteboard)

        # pylint: disable=E0702
        if test_exception is not None:
            raise test_exception
        elif cleanup_exception is not None:
            raise exceptions.TestSetupFail(cleanup_exception)
        elif stdout_check_exception is not None:
            raise stdout_check_exception
        elif stderr_check_exception is not None:
            raise stderr_check_exception
        elif self._Test__log_warn_used:
            raise exceptions.TestWarn("Test passed but there were warnings "
                                      "during execution. Check the log for "
                                      "details.")

        self.status = 'PASS'
        self.sysinfo_logger.end_test_hook()
