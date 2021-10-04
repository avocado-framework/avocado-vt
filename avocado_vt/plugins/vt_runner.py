import multiprocessing
import os
import time
import traceback

from avocado.core import exceptions, nrunner, teststatus
from avocado.core.runners.utils import messages
from avocado.core.test_id import TestID
from avocado.utils import astring

from avocado_vt import test


class VirtTest(test.VirtTest):

    def __init__(self, queue, runnable):
        self.queue = queue
        vt_params = runnable.kwargs
        vt_params['job_env_cleanup'] = 'no'
        kwargs = {'name': TestID(1, runnable.uri),
                  'config': runnable.config,
                  'vt_params': vt_params}
        super().__init__(**kwargs)

    def _save_log_dir(self):
        """
        Sends the content of vt logdir to avocado logdir
        """
        for root, _, files in os.walk(self.logdir, topdown=False):
            basedir = os.path.relpath(root, start=self.logdir)
            for file in files:
                file_path = os.path.join(root, file)
                with open(file_path, 'rb') as f:
                    base_path = os.path.join(basedir, file)
                    while True:
                        # Read data in manageable chunks rather than
                        # all at once.
                        in_data = f.read(200000)
                        if not in_data:
                            break
                        self.queue.put(messages.FileMessage.get(in_data,
                                                                base_path))

    def runTest(self):
        status = "PASS"
        fail_reason = ""
        try:
            messages.start_logging(self._config, self.queue)
            self.setUp()
            if isinstance(self.__status, Exception):
                # pylint doesn't know much about flow-control
                raise self.__status  # pylint: disable-msg=E0702
        except exceptions.TestBaseException as detail:
            status = detail.status
            fail_reason = (astring.to_text(detail))
            if status == "ERROR" or status not in teststatus.STATUSES:
                status = "ERROR"
                self.queue.put(messages.StderrMessage.get(traceback.format_exc()))
            else:
                self.queue.put(messages.LogMessage.get(traceback.format_exc()))
        except Exception as detail:
            status = "ERROR"
            try:
                fail_reason = (astring.to_text(detail))
            except TypeError:
                fail_reason = ("Unable to get exception, check the traceback "
                               "in `debug.log` for details.")
            self.queue.put(messages.StderrMessage.get(traceback.format_exc()))
        finally:
            self._save_log_dir()
            self.queue.put(messages.FinishedMessage.get(status, fail_reason))


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
        yield messages.StartedMessage.get()
        if self.runnable.config.get("nrunner.max_parallel_tasks", 1) != 1:
            yield messages.FinishedMessage.get('cancel',
                                               fail_reason="parallel run is not"
                                               " allowed for vt tests")
        else:
            try:
                queue = multiprocessing.SimpleQueue()
                vt_test = VirtTest(queue, self.runnable)
                process = multiprocessing.Process(target=vt_test.runTest)
                process.start()
                while True:
                    time.sleep(nrunner.RUNNER_RUN_CHECK_INTERVAL)
                    if queue.empty():
                        yield messages.RunningMessage.get()
                    else:
                        message = queue.get()
                        yield message
                        if message.get('status') == 'finished':
                            break
            except Exception:
                yield messages.StderrMessage.get(traceback.format_exc())
                yield messages.FinishedMessage.get('error')


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
