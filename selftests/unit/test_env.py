import unittest
from unittest import mock

from avocado_vt.plugins.env import Environment
from virttest.utils_params import Params


class EnvironmentTest(unittest.TestCase):
    @mock.patch("avocado_vt.plugins.env.intertest.load_addons_tools")
    @mock.patch("avocado_vt.plugins.env.cmd_parser.configure_runtime")
    @mock.patch("avocado_vt.plugins.env.cmd_parser.params_from_cmd")
    @mock.patch("avocado_vt.plugins.env.settings.update_option")
    def test_enforces_stateful_runtime_parameters(
        self, update_option, params_from_cmd, configure_runtime, load_addons_tools
    ):
        config = Params({"vt.env.params": ["setup="]})
        params_from_cmd.side_effect = lambda parsed: parsed.update(
            {"vms_params": Params({"setup": ""})}
        )

        self.assertEqual(Environment().run(config), 0)

        self.assertEqual(config["vt.common.tmp_dir"], "/tmp")
        update_option.assert_called_once_with("vt.common.tmp_dir", "/tmp")
        self.assertEqual(
            config["params"],
            [
                "setup=",
                "use_states=yes",
                "keep_vms_after_test=yes",
                "job_env_cleanup=no",
            ],
        )
        configure_runtime.assert_called_once_with(config, use_states=True)
        load_addons_tools.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
