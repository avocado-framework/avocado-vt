#!/usr/bin/env python3

import importlib
import sys
import unittest
from pathlib import Path
from unittest import mock

from avocado.core.resolver import ReferenceResolutionResult

from avocado_vt.plugins.loader import TestLoader
from avocado_vt.plugins.multivm import MultiVM
from avocado_vt.plugins.vt_resolver import VTResolver
from virttest import env_process
from virttest.states import ramfile
from virttest.states import setup as state_setup
from virttest.utils_env import Env
from virttest.utils_params import Params
from virttest.vmnet import setup_vmnet


class MultiVMLoaderTest(unittest.TestCase):
    def setUp(self):
        self.params = {"vm_type": "qemu", "mem": "2048", "use_states": "no"}
        self.config = {
            "run.vt_multi_vm": True,
            "list.vt_multi_vm": False,
            "run.suite_runner": "nrunner",
            "param_dict": self.params,
            "tests_str": "only tutorial2\n",
            "vm_strs": {"vm1": "only Fedora\n", "vm2": "only Win7\n"},
        }
        self.loader = TestLoader(config=self.config, extra_params={})

    @mock.patch("avocado_vt.plugins.loader.TestGraph")
    def test_nrunner_expands_composite_nodes(self, graph_class):
        flat_net = object()
        graph = graph_class.return_value
        graph_class.parse_net_from_object_restrs.return_value = flat_net
        graph.parse_composite_nodes.return_value = ["node-1", "node-2"]

        resolution = self.loader.resolve("only tutorial2")

        self.assertEqual(resolution.result, ReferenceResolutionResult.SUCCESS)
        self.assertEqual(resolution.resolutions, ["node-1", "node-2"])
        graph_class.parse_net_from_object_restrs.assert_called_once_with(
            "net1", self.config["vm_strs"]
        )
        graph.parse_composite_nodes.assert_called_once_with(
            self.config["tests_str"], flat_net, params=self.params
        )
        graph_class.parse_flat_nodes.assert_not_called()

    @mock.patch("avocado_vt.plugins.loader.TestGraph")
    def test_traverser_keeps_flat_nodes(self, graph_class):
        self.config["run.suite_runner"] = "traverser"
        graph_class.parse_flat_nodes.return_value = ["flat-1", "flat-2"]

        resolution = self.loader.resolve("only tutorial2")

        self.assertEqual(resolution.result, ReferenceResolutionResult.SUCCESS)
        self.assertEqual(resolution.resolutions, ["flat-1", "flat-2"])
        graph_class.parse_flat_nodes.assert_called_once_with(
            self.config["tests_str"], self.params
        )
        graph_class.parse_net_from_object_restrs.assert_not_called()

    @mock.patch("avocado_vt.plugins.loader.TestGraph")
    def test_empty_resolution_is_not_found_for_both_runners(self, graph_class):
        graph_class.return_value.parse_composite_nodes.return_value = []
        resolution = self.loader.resolve("only tutorial2")
        self.assertEqual(resolution.result, ReferenceResolutionResult.NOTFOUND)

        self.config["run.suite_runner"] = "traverser"
        graph_class.parse_flat_nodes.return_value = []
        resolution = self.loader.resolve("only tutorial2")
        self.assertEqual(resolution.result, ReferenceResolutionResult.NOTFOUND)


class MultiVMResolverRoutingTest(unittest.TestCase):
    @mock.patch("avocado_vt.plugins.multivm.settings.register_option")
    def test_cli_exposes_namespaced_independent_switches(self, register_option):
        parser = mock.Mock()
        parser.subcommands.choices = {
            "run": mock.Mock(),
            "list": mock.Mock(),
        }

        plugin = MultiVM()
        plugin.configure(parser)

        self.assertEqual(plugin.name, "multivm")
        options = {
            (call.kwargs["section"], call.kwargs["long_arg"])
            for call in register_option.call_args_list
        }
        self.assertEqual(
            options,
            {
                ("run", "--vt-multi-vm"),
                ("run", "--vt-states"),
                ("list", "--vt-multi-vm"),
            },
        )

    def test_regular_vt_resolver_yields_to_multi_vm_loader(self):
        resolver = VTResolver(config={"run.vt_multi_vm": True})
        with mock.patch.object(resolver, "_get_reference_resolution") as resolve:
            resolution = resolver.resolve("only tutorial2")

        self.assertEqual(resolution.result, ReferenceResolutionResult.NOTFOUND)
        resolve.assert_not_called()

    @mock.patch("avocado_vt.plugins.multivm.cmd_parser.configure_runtime")
    @mock.patch("avocado_vt.plugins.multivm.cmd_parser.params_from_cmd")
    def test_multi_vm_preparation_preserves_selected_runner(
        self, params_from_cmd, configure_runtime
    ):
        config = {
            "run.vt_multi_vm": True,
            "list.vt_multi_vm": False,
            "run.vt_states": False,
            "run.suite_runner": "traverser",
            "resolver.references": ["only tutorial2"],
            "params": [],
            "vt.type": "qemu",
            "vt.extra_params": ["mem=2048"],
        }

        MultiVM().run(config)

        self.assertEqual(config["run.suite_runner"], "traverser")
        params_from_cmd.assert_called_once_with(
            config,
            reference="only tutorial2",
            extra_params=["mem=2048", "vm_type=qemu", "use_states=no"],
        )
        configure_runtime.assert_called_once_with(config, use_states=False)

    @mock.patch("avocado_vt.plugins.multivm.cmd_parser.configure_runtime")
    @mock.patch("avocado_vt.plugins.multivm.cmd_parser.params_from_cmd")
    def test_state_handling_does_not_select_a_runner(
        self, params_from_cmd, configure_runtime
    ):
        config = {
            "run.vt_multi_vm": True,
            "list.vt_multi_vm": False,
            "run.vt_states": True,
            "run.suite_runner": "nrunner",
            "resolver.references": ["only tutorial2"],
            "params": [],
            "vt.type": "qemu",
            "vt.extra_params": [],
        }

        MultiVM().run(config)

        self.assertEqual(config["run.suite_runner"], "nrunner")
        params_from_cmd.assert_called_once_with(
            config,
            reference="only tutorial2",
            extra_params=[
                "vm_type=qemu",
                "use_states=yes",
                "keep_vms_after_test=yes",
                "job_env_cleanup=no",
            ],
        )
        self.assertEqual(config["vt.common.tmp_dir"], "/tmp")
        configure_runtime.assert_called_once_with(config, use_states=True)


class MultiVMControlTest(unittest.TestCase):
    def setUp(self):
        self.suite_path = Path(__file__).resolve().parents[2] / "tp_multivm"
        self.utility_path = str(self.suite_path / "utils")
        self.control_path = self.suite_path / "controls" / "pre_test.control"
        self.utility_was_present = self.utility_path in sys.path
        self.original_hooks = (
            env_process.preprocess_vm_off_hook,
            env_process.preprocess_vm_on_hook,
            env_process.postprocess_vm_on_hook,
            env_process.postprocess_vm_off_hook,
        )
        self.original_backends = state_setup.BACKENDS
        self.original_image_backend = ramfile.RamfileBackend.image_state_backend

    def tearDown(self):
        (
            env_process.preprocess_vm_off_hook,
            env_process.preprocess_vm_on_hook,
            env_process.postprocess_vm_on_hook,
            env_process.postprocess_vm_off_hook,
        ) = self.original_hooks
        state_setup.BACKENDS = self.original_backends
        ramfile.RamfileBackend.image_state_backend = self.original_image_backend
        if not self.utility_was_present and self.utility_path in sys.path:
            sys.path.remove(self.utility_path)
        sys.modules.pop("sample_utility", None)

    def _execute_control(self, use_states):
        params = Params(
            {
                "suite_path": str(self.suite_path),
                "start_vm": "no",
                "start_vm_vm1": "no",
                "vms": "vm1 vm2",
                "use_states": "yes" if use_states else "no",
            }
        )
        namespace = {"params": params}
        exec(self.control_path.read_text(encoding="utf-8"), namespace)
        return params

    def test_state_free_control_exposes_utilities_network_and_vm_startup(self):
        with mock.patch("virttest.vmnet.setup_vmnet") as setup_vmnet_mock:
            params = self._execute_control(use_states=False)

            self.assertEqual(sys.path[1], self.utility_path)
            sample_utility = importlib.import_module("sample_utility")
            self.assertTrue(callable(sample_utility.sleep))
            self.assertEqual(params["start_vm"], "yes")
            self.assertEqual(params["start_vm_vm1"], "yes")
            self.assertEqual(params["start_vm_vm2"], "yes")
            self.assertIsNone(env_process.preprocess_vm_on_hook)
            self.assertIsNone(env_process.postprocess_vm_on_hook)
            self.assertIsNone(env_process.postprocess_vm_off_hook)

            test, hook_params, env = object(), object(), object()
            env_process.preprocess_vm_off_hook(test, hook_params, env)
            setup_vmnet_mock.assert_called_once_with(hook_params, env)

    def test_stateful_control_composes_vmnet_and_state_hooks(self):
        calls = []
        with (
            mock.patch(
                "virttest.states.hooks.setup_vmnet_hook",
                side_effect=lambda *_args: calls.append("vmnet"),
            ) as vmnet_hook,
            mock.patch(
                "virttest.states.hooks.setup.get_states",
                side_effect=lambda *_args: calls.append("states"),
            ) as get_states,
        ):
            self._execute_control(use_states=True)
            test, params, env = object(), Params(), object()
            env_process.preprocess_vm_off_hook(test, params, env)

            vmnet_hook.assert_called_once_with(test, params, env)
            get_states.assert_called_once_with(params, env)
            self.assertEqual(calls, ["states", "vmnet"])
            self.assertTrue(callable(env_process.preprocess_vm_on_hook))
            self.assertTrue(callable(env_process.postprocess_vm_on_hook))
            self.assertTrue(callable(env_process.postprocess_vm_off_hook))


class VMNetworkSetupTest(unittest.TestCase):
    def test_attaches_and_reuses_prepared_network_without_state_backend(self):
        params = object()
        env = Env()
        env.start_ip_sniffing = mock.Mock()
        network_class = mock.Mock()
        vmnet = network_class.return_value

        result = setup_vmnet(params, env, network_class)
        reused = setup_vmnet(params, env, network_class)

        env.start_ip_sniffing.assert_called_once_with(params)
        network_class.assert_called_once_with(params, env)
        vmnet.setup_host_bridges.assert_called_once_with()
        vmnet.setup_host_services.assert_called_once_with()
        self.assertIs(result, vmnet)
        self.assertIs(reused, vmnet)
        self.assertIs(env.get_vmnet(), vmnet)


if __name__ == "__main__":
    unittest.main()
