import multiprocessing
import os
import tempfile
import time

from avocado.core import nrunner
from avocado_vt import utils
from virttest import (bootstrap, data_dir, env_process, utils_env, utils_misc,
                      utils_params)


class FakeTest:

    def __init__(self):
        self.iteration = 1
        self.logdir = tempfile.mkdtemp()
        self.debugdir = tempfile.mkdtemp()
        self.bindir = data_dir.get_root_dir()
        self.virtdir = os.path.join(self.bindir, 'shared')
        self.tmpdir = tempfile.mkdtemp()
        self.outputdir = os.path.join(self.logdir, 'data')
        os.mkdir(self.outputdir)

    def verify_background_errors(self):
        pass

    def write_test_keyval(self, info):
        pass


class VTTestRunner(nrunner.BaseRunner):
    """
    Runner for Avocado-VT (aka VirtTest) tests

    Runnable attributes usage:

     * uri: name of VT test

     * args: not used

     * kwargs: all the VT specific parameters
    """
    DEFAULT_TIMEOUT = 86400

    def _run_test_function(self):
        """simplified version of avocado_vt.test.VirtTest._runTest()"""
        params = utils_params.Params(**self.runnable.kwargs)
        fake_test = FakeTest()
        test_filter = bootstrap.test_filter
        subtest_dirs = utils.find_subtest_dirs(params.get("other_tests_dirs", ""),
                                               fake_test.bindir,
                                               test_filter)
        provider = params.get("provider", None)

        if provider is None:
            subtest_dirs += utils.find_generic_specific_subtest_dirs.params.get(
                "vm_type", test_filter)
        else:
            subtest_dirs += utils.find_provider_subtest_dirs(provider,
                                                             test_filter)
        subtest_dir = None
        t_types = params.get("type").split()
        utils.insert_dirs_to_path(subtest_dirs)
        test_modules = utils.find_test_modules(t_types, subtest_dirs)

        for t_type in t_types:
            test_module = test_modules[t_type]
            run_func = utils_misc.get_test_entrypoint_func(t_type, test_module)
            try:
                env_filename = os.path.join(data_dir.get_tmp_dir(),
                                            params.get("env", "env"))
                env = utils_env.Env(env_filename, '1')
                params = env_process.preprocess(fake_test, params, env)
                run_func(fake_test, params, env)
                env_process.postprocess(fake_test, params, env)
            except Exception as e:
                return {'result': 'error',
                        'error': str(e)}
        return {'result': 'pass'}

    def run(self):
        yield self.prepare_status('started')
        run_result = self._run_test_function()
        yield self.prepare_status('finished', run_result)


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
