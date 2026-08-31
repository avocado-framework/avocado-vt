import unittest
from unittest import mock

from avocado.plugins.runners.avocado_instrumented import (
    AvocadoInstrumentedTestRunner,
)

from avocado_vt.plugins import vt_runner


class VTTestRunnerConfigurationTest(unittest.TestCase):
    @mock.patch("avocado_vt.plugins.vt_runner.settings")
    def test_applies_serialized_runner_settings(self, runner_settings):
        runner_settings.as_dict.return_value = {"core.show": None}
        config = {
            "core.show": ["app"],
            "vt.common.tmp_dir": "/tmp",
        }

        vt_runner._configure_runner_settings(config)

        runner_settings.register_option.assert_called_once_with(
            section="vt.common",
            key="tmp_dir",
            key_type=str,
            default="/tmp",
            help_msg="Configuration forwarded to the standalone runner",
        )
        runner_settings.update_option.assert_has_calls(
            [
                mock.call("core.show", ["app"]),
                mock.call("vt.common.tmp_dir", "/tmp"),
            ]
        )
        self.assertIn("vt.common.tmp_dir", vt_runner.VTTestRunner.CONFIGURATION_USED)

    def test_reuses_hardened_instrumented_runner_monitor(self):
        self.assertTrue(vt_runner.PROCESS_MONITOR_AVAILABLE)
        self.assertIs(
            vt_runner.VTTestRunner._monitor,
            AvocadoInstrumentedTestRunner._monitor,
        )
        self.assertIs(
            vt_runner.VTTestRunner._cleanup_process.__func__,
            AvocadoInstrumentedTestRunner._cleanup_process.__func__,
        )


if __name__ == "__main__":
    unittest.main()
