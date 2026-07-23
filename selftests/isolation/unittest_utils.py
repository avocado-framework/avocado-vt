import unittest.mock as mock
import re
import asyncio

from aexpect.exceptions import ShellCmdError
from avocado.core import exceptions


class DummyTestRun(object):

    asserted_tests = []

    def __init__(self, node_params, test_results):
        self.test_results = test_results
        # assertions about the test calls
        self.current_test_dict = node_params
        shortname = self.current_test_dict["shortname"]

        assert len(self.asserted_tests) > 0, "Unexpected test %s" % shortname
        self.expected_test_dict = self.asserted_tests.pop(0)
        for checked_key in self.expected_test_dict.keys():
            if checked_key.startswith("_"):
                continue
            assert checked_key in self.current_test_dict.keys(), "%s missing in %s (params: %s)" % (checked_key, shortname, self.current_test_dict)
            expected, current = self.expected_test_dict[checked_key], self.current_test_dict[checked_key]
            assert re.match(expected, current) is not None, "Expected parameter %s=%s "\
                                                            "but obtained %s=%s for %s (params: %s)" % (checked_key, expected,
                                                                                                        checked_key, current,
                                                                                                        self.expected_test_dict["shortname"],
                                                                                                        self.current_test_dict)

    def get_test_result(self):
        uid = self.current_test_dict["_uid"]
        name = self.current_test_dict["name"]
        # allow tests to specify the status they expect
        status = self.expected_test_dict.get("_status", "PASS")
        time_elapsed = self.expected_test_dict.get("_time_elapsed", "1")
        self.add_test_result(uid, name, status, time_elapsed)
        if status in ["ERROR", "FAIL"] and self.current_test_dict.get("abort_on_error", "no") == "yes":
            raise exceptions.TestSkipError("God wanted this test to abort")
        return status not in ["ERROR", "FAIL"]

    def add_test_result(self, uid, name, status, time_elapsed, logdir="."):
        mocktestid = type("Mock", (), {"uid": uid, "name": name})()
        # or else have to set name attribute separately since "name" is reserved by MagicMock
        # mocktestid = mock.MagicMock(uid=uid, name=name)
        # mocktestid.name = name
        self.test_results.append({
            "name": mocktestid,
            "status": status,
            "time_elapsed": time_elapsed,
            "logdir": logdir,
        })

    @staticmethod
    async def mock_run_test_task(self, node):
        if not hasattr(self.job, "result"):
            self.job.result = mock.MagicMock()
            self.job.result.tests = []
        # provide ID-s and other node attributes as meta-parameters for assertion
        node.params["_long_prefix"] = node.long_prefix
        node.params["_uid"] = node.id_test.uid
        assert node.started_worker is not None, f"{node} was not properly started by any worker"
        assert "UNKNOWN" in [r["status"] for r in node.results], f"{node} does not have current UNKNOWN result"
        # small enough not to slow down our tests too much for a test timeout of 300 but
        # large enough to surpass the minimal occupation waiting timeout for more realism
        await asyncio.sleep(0.1)
        return DummyTestRun(node.params, self.job.result.tests).get_test_result()


class DummyStateControl(object):

    asserted_states = {"check": {}, "get": {}, "set": {}, "unset": {}}
    states_params = {}
    action = "check"

    def __init__(self):
        params = self.states_params
        do = self.action
        self.result = True

        for vm in params.objects("vms"):
            vm_params = params.object_params(vm)
            for image in params.objects("images"):
                image_params = vm_params.object_params(image)
                do_loc = "show" if do == "check" else do
                do_source = image_params.get(f"{do_loc}_location_images", "")
                do_state = image_params.get(f"{do}_state_images")
                if not do_state:
                    do_state = image_params.get(f"{do}_state_vms")
                    do_source = image_params.get(f"{do_loc}_location_vms", "")
                    if not do_state:
                        continue

                assert do_state in self.asserted_states[do], f"Unexpected state {do_state} to {do}"
                assert do_source != "", f"Empty {do} state location for {do_state}"
                do_sources = do_source.split()
                for do_source in do_sources:
                    # TODO: currently we cannot fully test additional state sources
                    if not do_source.endswith("shared"):
                        continue
                    if do == "check":
                        if not self.asserted_states[do][do_state][do_source] and len(do_sources) == 1:
                            self.result = False
                    else:
                        self.asserted_states[do][do_state][do_source] += 1

    @staticmethod
    def run_subcontrol(session, mod_control_path):
        if not DummyStateControl().result:
            raise ShellCmdError(1, "command", "AssertionError")

    @staticmethod
    def set_subcontrol_parameter(_, __, do):
        DummyStateControl.action = do

    @staticmethod
    def set_subcontrol_parameter_dict(_, __, node_params):
        DummyStateControl.states_params = node_params
