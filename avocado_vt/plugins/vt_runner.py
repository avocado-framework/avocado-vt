import logging
import multiprocessing
import os
import pickle
import sys
import tempfile
import time
import traceback

from avocado.core import exceptions, nrunner, output, test, teststatus, test_id
from avocado.utils import genio, stacktrace, path

from avocado_vt import utils
from virttest import (bootstrap, data_dir, env_process, error_event, utils_env,
                      utils_misc, utils_params, version, funcatexit)

BG_ERR_FILE = "background-error.log"


class VirtTest:

    def __init__(self, queue, vt_params=None):
        self.__vt_params = utils_params.Params(vt_params)
        self.queue = queue
        self.tmpdir = tempfile.mkdtemp()
        self.logdir = os.path.join(self.tmpdir, 'results')
        path.init_dir(self.logdir)
        self.logfile = os.path.join(self.logdir, 'debug.log')
        self.log = output.LOG_JOB
        self.env_version = utils_env.get_env_version()
        self.iteration = 0
        self.background_errors = error_event.error_events_bus
        # clear existing error events
        self.background_errors.clear()
        self.debugdir = self.logdir
        self.bindir = data_dir.get_root_dir()
        self.virtdir = os.path.join(self.bindir, 'shared')


    @property
    def params(self):
        return self.__vt_params

    def write_test_keyval(self, info):
        pass

    def __safe_env_save(self, env):
        """
        Treat "env.save()" exception as warnings

        :param env: The virttest env object
        :return: True on failure
        """
        try:
            env.save()
        except Exception as details:
            try:
                pickle.dumps(env.data)
            except Exception:
                self.log.warn("Unable to save environment: %s",
                              stacktrace.str_unpickable_object(env.data))
            else:
                self.log.warn("Unable to save environment: %s (%s)", details,
                              env.data)
            return True
        return False

    def _start_logging(self):
        """
        Simple helper for adding a file logger to the root logger.
        """
        file_handler = logging.FileHandler(filename=self.logfile)
        file_handler.setLevel(logging.DEBUG)

        fmt = '%(asctime)s %(levelname)-5.5s| %(message)s'
        formatter = logging.Formatter(fmt=fmt, datefmt='%H:%M:%S')

        file_handler.setFormatter(formatter)
        self.log.setLevel(logging.DEBUG)
        self.log.addHandler(file_handler)
        self.log.propagate = False
        logging.root.addHandler(file_handler)

    def verify_background_errors(self):
        """
        Verify if there are any errors that happened on background threads.
        Logs all errors in the background_errors into background-error.log and
        error the test.
        """
        err_file_path = os.path.join(self.logdir, BG_ERR_FILE)
        bg_errors = self.background_errors.get_all()
        error_messages = ["BACKGROUND ERROR LIST:"]
        for index, error in enumerate(bg_errors):
            error_messages.append(
                "- ERROR #%d -\n%s" % (index, "".join(
                    traceback.format_exception(*error)
                )))
        genio.write_file(err_file_path, '\n'.join(error_messages))
        if bg_errors:
            msg = ["Background error", "s are" if len(bg_errors) > 1 else " is",
                   " detected, please refer to file: '%s' for more details." %
                   BG_ERR_FILE]
            self.error(''.join(msg))

    def runTest(self):
        try:
            self._start_logging()
            params = self.params

            # If a dependency test prior to this test has failed, let's fail
            # it right away as TestNA.
            if params.get("dependency_failed") == 'yes':
                raise exceptions.TestSkipError("Test dependency failed")

            # Report virt test version
            self.log.info(version.get_pretty_version_info())
            # Report the parameters we've received and write them as keyvals
            self.log.debug("Test parameters:")
            keys = list(params.keys())
            keys.sort()
            for key in keys:
                self.log.debug("    %s = %s", key, params[key])

            # Warn of this special condition in related location in output & logs
            if os.getuid() == 0 and params.get('nettype', 'user') == 'user':
                self.log.warning("")
                self.log.warning("Testing with nettype='user' while running "
                                 "as root may produce unexpected results!!!")
                self.log.warning("")

            test_filter = bootstrap.test_filter
            subtest_dirs = utils.find_subtest_dirs(params.get(
                "other_tests_dirs", ""), self.bindir, test_filter)
            provider = params.get("provider", None)

            if provider is None:
                subtest_dirs += utils.find_generic_specific_subtest_dirs.\
                    params.get("vm_type", test_filter)
            else:
                subtest_dirs += utils.find_provider_subtest_dirs(provider,
                                                                 test_filter)

            # Get the test routine corresponding to the specified
            # test type
            self.log.debug("Searching for test modules that match 'type = %s' "
                           "and 'provider = %s' on this cartesian dict",
                           params.get("type"),
                           params.get("provider", None))

            t_types = params.get("type").split()
            utils.insert_dirs_to_path(subtest_dirs)
            test_modules = utils.find_test_modules(t_types, subtest_dirs)

            # Open the environment file
            env_filename = os.path.join(data_dir.get_tmp_dir(),
                                        params.get("env", "env"))
            env = utils_env.Env(env_filename, self.env_version)

            test_passed = False
            t_type = None


            try:
                try:
                    # Pre-process
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
                        raise exceptions.TestWarn("funcatexit failed with: %s" %
                                                  error_message)

                except:  # nopep8 Old-style exceptions are not inherited from Exception()
                    stacktrace.log_exc_info(sys.exc_info(), 'avocado.test')
                    if t_type is not None:
                        error_message = funcatexit.run_exitfuncs(env, t_type)
                        if error_message:
                            self.log.error(error_message)
                    try:
                        env_process.postprocess_on_error(self, params, env)
                    finally:
                        self.__safe_env_save(env)
                    raise

            finally:
                # Post-process
                try:
                    try:
                        params['test_passed'] = str(test_passed)
                        env_process.postprocess(self, params, env)
                    except:  # nopep8 Old-style exceptions are not inherited from Exception()

                        stacktrace.log_exc_info(sys.exc_info(),
                                                'avocado.test')
                        if test_passed:
                            raise
                        self.log.error("Exception raised during postprocessing:"
                                       " %s", sys.exc_info()[1])
                finally:
                    if self.__safe_env_save(env) or params.get("env_cleanup",
                                                               "no") == "yes":
                        env.destroy()  # Force-clean as it can't be stored

        except Exception as e:
            if params.get("abort_on_error") != "yes":
                self.queue.put({'result': "ERROR", 'error': str(e)})
            # Abort on error
            self.log.info("Aborting job (%s)", e)
            if params.get("vm_type") == "qemu":
                for vm in env.get_all_vms():
                    if vm.is_dead():
                        continue
                    self.log.info("VM '%s' is alive.", vm.name)
                    for m in vm.monitors:
                        self.log.info("It has a %s monitor unix socket at: %s",
                                     m.protocol, m.filename)
                    self.log.info("The command line used to start it was:\n%s",
                                 vm.make_create_command())
                self.queue.put({'result': "ERROR",
                                'error': str(exceptions.JobError(
                                    "Abort requested (%s)" % e))})
        self.queue.put({'result': "PASS"})


class VTTestRunner(nrunner.BaseRunner):
    """
    Runner for Avocado-VT (aka VirtTest) tests

    Runnable attributes usage:

     * uri: name of VT test

     * args: not used

     * kwargs: all the VT specific parameters
    """
    DEFAULT_TIMEOUT = 86400

    def run(self):
        yield self.prepare_status('started')
        queue = multiprocessing.SimpleQueue()
        vt_test = VirtTest(queue, self.runnable.kwargs)
        process = multiprocessing.Process(target=vt_test.runTest)
        process.start()
        while True:
            time.sleep(nrunner.RUNNER_RUN_CHECK_INTERVAL)
            if not queue.empty():
                state = queue.get()
                if state.get("result") in teststatus.user_facing_status:
                    break
            yield self.prepare_status('running')
        state['status'] = 'finished'
        state['logdir'] = vt_test.logdir
        state['logfile'] = vt_test.logfile
        state['time'] = time.monotonic()
        yield state


class RunnerApp(nrunner.BaseRunnerApp):
    PROG_NAME = 'avocado-runner-avocado-vt'
    PROG_DESCRIPTION = 'nrunner application for Avocado-VT tests'
    RUNNABLE_KINDS_CAPABLE = {
        'avocado-vt': VTTestRunner
    }


def main():
    nrunner.main(RunnerApp)


if __name__ == '__main__':
    main()
