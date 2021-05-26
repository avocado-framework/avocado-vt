import logging
import multiprocessing
import os
import sys
import tempfile
import time
import traceback

from avocado.core import exceptions, nrunner, output
from avocado.utils import stacktrace, path

from avocado_vt import utils
from virttest import (data_dir, env_process, error_event, utils_env, utils_misc,
                      utils_params, version, funcatexit)


def _send_message(msg, queue, message_type):
    status = {'type': message_type, 'log': msg}
    queue.put(status)


class RunnerLogHandler(logging.Handler):

    def __init__(self, queue, message_type):
        """
        Runner logger which will put every log message to the runner queue

        :param queue: queue for the runner messages
        :type queue: :class: multiprocessing.SimpleQueue
        :param message_type: type of the log message
        :type message_type: string with possible values: {stdout, stderr, log}
        """
        super().__init__()
        self.queue = queue
        self.message_type = message_type

    def emit(self, record):
        msg = self.format(record)
        _send_message(msg, self.queue, self.message_type)


class StreamToQueue:

    def __init__(self, queue, message_type):
        """
        Runner Stream which will transfer every message to the runner queue

        :param queue: queue for the runner messages
        :type queue: multiprocessing.SimpleQueue
        :param message_type: type of the log
        :type message_type: string
        """
        self.queue = queue
        self.message_type = message_type

    def write(self, buf):
        _send_message(buf, self.queue, self.message_type)

    def flush(self):
        pass


class VirtTest(utils.TestUtils):

    def __init__(self, queue, runnable):
        self.__vt_params = utils_params.Params(runnable.kwargs)
        self.queue = queue
        self.tmpdir = tempfile.mkdtemp()
        self.logdir = os.path.join(self.tmpdir, 'results')
        path.init_dir(self.logdir)
        self.logfile = os.path.join(self.logdir, 'debug.log')
        self.log = output.LOG_JOB
        self.log_level = runnable.config.get('job.output.loglevel',
                                             logging.DEBUG)
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

    def _start_logging(self):
        """Simple helper for adding a file logger to the root logger."""
        file_handler = logging.FileHandler(filename=self.logfile)
        log_handler = RunnerLogHandler(self.queue, 'log')

        fmt = ('%(asctime)s %(module)-16.16s L%(lineno)-.4d %('
               'levelname)-5.5s| %(message)s')
        formatter = logging.Formatter(fmt=fmt)

        file_handler.setFormatter(formatter)
        log_handler.setFormatter(formatter)
        self.log.setLevel(self.log_level)
        self.log.addHandler(file_handler)
        self.log.addHandler(log_handler)
        self.log.propagate = False
        logging.root.addHandler(file_handler)
        logging.root.addHandler(log_handler)
        logging.root.setLevel(self.log_level)
        output.LOG_UI.addHandler(RunnerLogHandler(self.queue, 'stdout'))

        sys.stdout = StreamToQueue(self.queue, "stdout")
        sys.stderr = StreamToQueue(self.queue, "stderr")

    def run_test(self):
        params = self.params
        try:
            self._start_logging()

            # Report virt test version
            self.log.info(version.get_pretty_version_info())
            self._log_parameters()

            # Warn of this special condition in related location in output & logs
            if os.getuid() == 0 and params.get('nettype', 'user') == 'user':
                self.log.warning("")
                self.log.warning("Testing with nettype='user' while running "
                                 "as root may produce unexpected results!!!")
                self.log.warning("")

            subtest_dirs = self._get_subtest_dirs()

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
                        self._safe_env_save(env)

                    # Run the test function
                    for t_type in t_types:
                        test_module = test_modules[t_type]
                        run_func = utils_misc.get_test_entrypoint_func(
                            t_type, test_module)
                        try:
                            run_func(self, params, env)
                            self.verify_background_errors()
                        finally:
                            self._safe_env_save(env)
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
                        self._safe_env_save(env)
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
                    if self._safe_env_save(env) or params.get("env_cleanup",
                                                              "no") == "yes":
                        env.destroy()  # Force-clean as it can't be stored

        except Exception as e:
            try:
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
                            logging.info("It has a %s monitor unix socket at:"
                                         " %s", m.protocol, m.filename)
                        logging.info("The command line used to start it was:"
                                     "\n%s", vm.make_create_command())
                    raise exceptions.JobError("Abort requested (%s)" % e)
            finally:
                self.queue.put({'type': 'stderr',
                                'log': traceback.format_exc().encode('utf-8')})
                self.queue.put({'status': 'finished', 'result': 'error'})
        self.queue.put({'status': 'finished', 'result': 'pass'})


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
        try:
            queue = multiprocessing.SimpleQueue()
            vt_test = VirtTest(queue, self.runnable)
            process = multiprocessing.Process(target=vt_test.run_test)
            process.start()
            while True:
                time.sleep(nrunner.RUNNER_RUN_CHECK_INTERVAL)
                if queue.empty():
                    yield self.prepare_status('running',)
                else:
                    message = queue.get()
                    if message.get('status') == 'finished':
                        yield self.prepare_status('finished', message)
                        break
                    else:
                        yield self.prepare_status('running', message)
        except Exception:
            yield self.prepare_status('running',
                                      {'type': 'stderr',
                                       'log': traceback.format_exc().encode(
                                           'utf-8')})
            yield self.prepare_status('finished', {'result': 'error'})


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
