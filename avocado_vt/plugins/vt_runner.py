import multiprocessing
import os
import time
import traceback

from avocado.core import exceptions, teststatus
from avocado.core.test_id import TestID
from avocado.utils import astring

from avocado_vt import test

# Compatibility with avocado 92.0 LTS version, this can be removed when
# the 92.0 support will be dropped.
try:
    from avocado.core.nrunner import (
        RUNNER_RUN_CHECK_INTERVAL,
        BaseRunner,
        BaseRunnerApp,
    )
    from avocado.core.nrunner import main as nrunner_main
    from avocado.core.runners.utils import messages

    LTS = True
except ImportError:
    from avocado.core.nrunner.app import BaseRunnerApp
    from avocado.core.nrunner.runner import RUNNER_RUN_CHECK_INTERVAL, BaseRunner
    from avocado.core.utils import messages

    LTS = False


class VirtTest(test.VirtTest):
    def __init__(self, queue, runnable):
        self.queue = queue
        base_logdir = getattr(runnable, "output_dir", None)
        vt_params = runnable.kwargs
        vt_params["job_env_cleanup"] = "no"
        kwargs = {
            "name": TestID(1, runnable.uri),
            "config": runnable.config,
            "base_logdir": base_logdir,
            "vt_params": vt_params,
        }
        super().__init__(**kwargs)

    def _save_log_dir(self):
        """
        Sends the content of vt logdir to avocado logdir
        """
        for root, _, files in os.walk(self.logdir, topdown=False):
            basedir = os.path.relpath(root, start=self.logdir)
            for file in files:
                file_path = os.path.join(root, file)
                with open(file_path, "rb") as f:
                    base_path = os.path.join(basedir, file)
                    while True:
                        # Read data in manageable chunks rather than
                        # all at once.
                        in_data = f.read(200000)
                        if not in_data:
                            break
                        self.queue.put(messages.FileMessage.get(in_data, base_path))

    def runTest(self):
        status = "PASS"
        fail_reason = ""
        fail_class = ""
        traceback_log = ""
        try:
            messages.start_logging(self._config, self.queue)
            self.setUp()
            if isinstance(self.__status, Exception):
                # pylint doesn't know much about flow-control
                raise self.__status  # pylint: disable-msg=E0702
        except exceptions.TestBaseException as detail:
            status = detail.status
            fail_reason = astring.to_text(detail)
            fail_class = detail.__class__.__name__
            traceback_log = traceback.format_exc()
            if status == "ERROR" or status not in teststatus.STATUSES:
                status = "ERROR"
                self.queue.put(messages.StderrMessage.get(traceback_log))
            else:
                self.queue.put(messages.LogMessage.get(traceback_log))
        except Exception as detail:
            status = "ERROR"
            try:
                fail_reason = astring.to_text(detail)
                fail_class = detail.__class__.__name__
                traceback_log = traceback.format_exc()
            except TypeError:
                fail_reason = (
                    "Unable to get exception, check the traceback "
                    "in `debug.log` for details."
                )
            self.queue.put(messages.StderrMessage.get(traceback_log))
        finally:
            self.queue.put(messages.WhiteboardMessage.get(self.whiteboard))
            if "avocado_test_" in self.logdir:
                self._save_log_dir()
            try:
                self.queue.put(
                    messages.FinishedMessage.get(
                        status,
                        fail_reason=fail_reason,
                        class_name="VirtTest",
                        fail_class=fail_class,
                        traceback=traceback_log,
                    )
                )
            except TypeError:
                self.queue.put(messages.FinishedMessage.get(status, fail_reason))


class VTTestRunner(BaseRunner):
    """
    Runner for Avocado-VT (aka VirtTest) tests

    Runnable attributes usage:

     * uri: name of VT test

     * args: not used

     * kwargs: all the VT specific parameters
    """

    name = "avocado-vt"
    description = "nrunner application for Avocado-VT tests"

    CONFIGURATION_USED = [
        "datadir.paths.cache_dirs",
        "core.show",
        "job.output.loglevel",
        "job.run.store_logging_stream",
    ]

    DEFAULT_TIMEOUT = 86400

    def run(self, runnable=None):
        if runnable:
            self.runnable = runnable

        yield messages.StartedMessage.get()
        if (
            self.runnable.config.get(
                "run.max_parallel_tasks",
                self.runnable.config.get("nrunner.max_parallel_tasks", 1),
            )
            != 1
        ):
            yield messages.FinishedMessage.get(
                "cancel", fail_reason="parallel run is not" " allowed for vt tests"
            )
        else:
            try:
                queue = multiprocessing.SimpleQueue()
                vt_test = VirtTest(queue, self.runnable)
                process = multiprocessing.Process(target=vt_test.runTest)
                process.start()
                while True:
                    time.sleep(RUNNER_RUN_CHECK_INTERVAL)
                    if queue.empty():
                        yield messages.RunningMessage.get()
                    else:
                        message = queue.get()
                        yield message
                        if message.get("status") == "finished":
                            break
            except Exception:
                yield messages.StderrMessage.get(traceback.format_exc())
                yield messages.FinishedMessage.get("error")


class RunnerApp(BaseRunnerApp):
    PROG_NAME = "avocado-runner-avocado-vt"
    PROG_DESCRIPTION = "nrunner application for Avocado-VT tests"
    if LTS:
        RUNNABLE_KINDS_CAPABLE = {"avocado-vt": VTTestRunner}
    else:
        RUNNABLE_KINDS_CAPABLE = ["avocado-vt"]


def main():
    if LTS:
        nrunner_main(RunnerApp)
    else:
        app = RunnerApp(print)
        app.run()


if __name__ == "__main__":
    main()
