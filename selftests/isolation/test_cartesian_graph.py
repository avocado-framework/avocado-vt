#!/usr/bin/env python

import unittest
import unittest.mock as mock
import asyncio

from avocado import Test, skip
from avocado.core import exceptions
from avocado.core.suite import TestSuite, resolutions_to_runnables
from avocado_vt.plugins.loader import TestLoader
from avocado_vt.plugins.runner import TestRunner
from virttest import params_parser as param
from virttest.cartgraph import *

import unittest_importer
from unittest_utils import DummyTestRun, DummyStateControl


class CartesianWorkerTest(Test):

    def setUp(self):
        self.config = {}
        self.config["param_dict"] = {"test_timeout": 100, "shared_pool": "/mnt/local/images/shared", "nets": "net1"}
        self.config["tests_str"] = "only normal\n"
        self.config["vm_strs"] = {"vm1": "only CentOS\n", "vm2": "only Win10\n", "vm3": "only Ubuntu\n"}

        self.prefix = ""

        self.loader = TestLoader(config=self.config, extra_params={})

    def test_parse_flat_objects_vm(self):
        """Test for correctly parsed objects of different object variants from a restriction."""
        test_objects = TestGraph.parse_flat_objects("vm1", "vms")
        self.assertEqual(len(test_objects), 2)
        self.assertRegex(test_objects[1].params["name"], r"vms.vm1\.qemu_kvm_centos.*CentOS.*")
        self.assertEqual(test_objects[1].params["vms"], "vm1")
        self.assertEqual(test_objects[1].params["os_variant"], "centos")
        self.assertRegex(test_objects[0].params["name"], r"vms.vm1\.qemu_kvm_fedora.*Fedora.*")
        self.assertEqual(test_objects[0].params["vms"], "vm1")
        self.assertEqual(test_objects[0].params["os_variant"], "fedora")

        test_object = TestGraph.parse_flat_objects("vm1", "vms", "CentOS", unique=True)
        self.assertRegex(test_object.params["name"], r"vms.vm1\.qemu_kvm_centos.*CentOS.*")

        test_object = TestGraph.parse_flat_objects("vm1", "vms", "no CentOS\nonly qcow2\n", unique=True)
        self.assertRegex(test_object.params["name"], r"vms.vm1\.qemu_kvm_fedora.*qcow2.*Fedora.*")

    def test_parse_flat_objects_net(self):
        """Test for correctly parsed objects of different object variants from a restriction."""
        test_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        self.assertRegex(test_object.params["name"], r"nets\.localhost\.net1")
        self.assertEqual(test_object.params["nets"], "net1")
        self.assertEqual(test_object.params["nets_id"], "101")

        test_object = TestGraph.parse_flat_objects("net1", "nets", "localhost", unique=True)
        self.assertRegex(test_object.params["name"], r"nets\.localhost\.net1")

        test_object = TestGraph.parse_flat_objects("net1", "nets", "no remotehost\nonly localhost\n", unique=True)
        self.assertRegex(test_object.params["name"], r"nets\.localhost\.net1")

    def test_parse_flat_objects_net_and_cluster(self):
        """Test for correctly parsed objects of different object variants from a restriction."""
        test_objects = TestGraph.parse_flat_objects("net6", "nets")
        self.assertEqual(len(test_objects), 3)
        self.assertRegex(test_objects[0].params["name"], r"nets\.localhost\.net6")
        self.assertEqual(test_objects[0].params["nets"], "net6")
        self.assertEqual(test_objects[0].params["nets_id"], "101")
        self.assertRegex(test_objects[1].params["name"], r"nets\.cluster1\.net6")
        self.assertEqual(test_objects[1].params["nets"], "net6")
        self.assertEqual(test_objects[1].params["nets_id"], "1")
        self.assertRegex(test_objects[2].params["name"], r"nets\.cluster2\.net6")
        self.assertEqual(test_objects[2].params["nets"], "net6")
        self.assertEqual(test_objects[2].params["nets_id"], "1")

        test_object = TestGraph.parse_flat_objects("net6", "nets", "cluster1", unique=True)
        self.assertRegex(test_object.params["name"], r"nets\.cluster1\.net6")

        test_object = TestGraph.parse_flat_objects("net6", "nets", "no cluster1\nonly cluster2\n", unique=True)
        self.assertRegex(test_object.params["name"], r"nets\.cluster2\.net6")

    def test_params(self):
        """Test for correctly parsed and regenerated test worker parameters."""
        test_workers = TestGraph.parse_workers({"nets": "net3 net4 net5"})
        self.assertEqual(len(test_workers), 3)
        test_worker = test_workers[0]
        for key in test_worker.params.keys():
            self.assertEqual(test_worker.net.params[key], test_worker.params[key],
                            f"The values of key {key} {test_worker.net.params[key]}={test_worker.params[key]} must be the same")

    def test_params_slots(self):
        """Test environment setting and validation."""
        test_workers = TestGraph.parse_workers({"nets": "net3 cluster1.net6 net0",
                                                "slots": "1 remote.com/2 "})
        self.assertEqual(len(test_workers), 3)
        self.assertEqual(test_workers[0].params["nets_gateway"], "")
        self.assertEqual(test_workers[0].params["nets_host"], "c1")
        self.assertEqual(test_workers[0].params["nets_spawner"], "lxc")
        self.assertEqual(test_workers[0].params["nets_shell_host"], "192.168.254.1")
        self.assertEqual(test_workers[0].params["nets_shell_port"], "22")
        self.assertEqual(test_workers[1].params["nets_gateway"], "remote.com")
        self.assertEqual(test_workers[1].params["nets_host"], "2")
        self.assertEqual(test_workers[1].params["nets_spawner"], "remote")
        self.assertEqual(test_workers[1].params["nets_shell_host"], "remote.com")
        self.assertEqual(test_workers[1].params["nets_shell_port"], "222")
        self.assertEqual(test_workers[2].params["nets_gateway"], "")
        self.assertEqual(test_workers[2].params["nets_host"], "")
        self.assertEqual(test_workers[2].params["nets_spawner"], "process")
        self.assertEqual(test_workers[2].params["nets_shell_host"], "localhost")
        self.assertEqual(test_workers[2].params["nets_shell_port"], "22")
        self.assertIn("localhost", TestSwarm.run_swarms)
        self.assertEqual(TestSwarm.run_swarms["localhost"].workers, [test_workers[0], test_workers[2]])
        self.assertIn("cluster1", TestSwarm.run_swarms)
        self.assertEqual(TestSwarm.run_swarms["cluster1"].workers, [test_workers[1]])

    def test_restrs(self):
        """Test for correctly parsed and regenerated test worker restrictions."""
        test_workers = TestGraph.parse_workers({"nets": "net3 net4 net5"})
        self.assertEqual(len(test_workers), 3)
        test_worker = test_workers[0]
        for key in test_worker.restrs.keys():
            self.assertEqual(test_worker.net.restrs[key], test_worker.restrs[key],
                             f"The restriction of key {key} {test_worker.net.restrs[key]}={test_worker.restrs[key]} must be the same")

    def test_sanity_in_graph(self):
        """Test generic usage and composition."""
        self.config["tests_str"] += "only tutorial1\n"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )
        self.assertEqual(len(graph.workers), 1)
        for i, worker_id in enumerate(graph.workers):
            self.assertEqual(f"net{i+1}", worker_id)
            worker = graph.workers[worker_id]
            self.assertEqual(worker_id, worker.id)
            self.assertIn("[worker]", str(worker))
            graph.new_workers(worker.net)


class CartesianObjectTest(Test):

    def setUp(self):
        self.config = {}
        self.config["param_dict"] = {"test_timeout": 100, "shared_pool": "/mnt/local/images/shared", "nets": "net1"}
        self.config["tests_str"] = "only normal\n"
        self.config["vm_strs"] = {"vm1": "only CentOS\n", "vm2": "only Win10\n", "vm3": "only Ubuntu\n"}

        self.prefix = ""

        self.loader = TestLoader(config=self.config, extra_params={})

    def test_parse_composite_objects_vm(self):
        """Test for correctly parsed vm objects from a vm string restriction."""
        test_objects = TestGraph.parse_composite_objects("vm1", "vms", "")
        self.assertEqual(len(test_objects), 2)
        self.assertRegex(test_objects[1].params["name"], r"vm1\.qemu_kvm_centos.*CentOS.*")
        self.assertEqual(test_objects[1].params["vms"], "vm1")
        self.assertEqual(test_objects[1].params["main_vm"], "vm1")
        self.assertEqual(test_objects[1].params["os_variant"], "centos")
        self.assertEqual(test_objects[1].params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")
        self.assertRegex(test_objects[0].params["name"], r"vm1\.qemu_kvm_fedora.*Fedora.*")
        self.assertEqual(test_objects[0].params["vms"], "vm1")
        self.assertEqual(test_objects[0].params["main_vm"], "vm1")
        self.assertEqual(test_objects[0].params["os_variant"], "fedora")
        self.assertEqual(test_objects[0].params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")
        self.assertNotIn("only", test_objects[0].params)

        test_object = TestGraph.parse_composite_objects("vm1", "vms", "CentOS", unique=True)
        self.assertRegex(test_object.params["name"], r"vm1\.qemu_kvm_centos.*CentOS.*")

        test_object = TestGraph.parse_composite_objects("vm1", "vms", "no CentOS\nonly qcow2\n", unique=True)
        self.assertRegex(test_object.params["name"], r"vms.vm1\.qemu_kvm_fedora.*qcow2.*Fedora.*")

    def test_parse_composite_objects_net(self):
        """Test for a correctly parsed net object from joined vm string restrictions."""
        test_object = TestGraph.parse_composite_objects("net1", "nets", "", self.config["vm_strs"], unique=True)
        self.assertRegex(test_object.params["name"], r"vm1\.qemu_kvm_centos.*CentOS.*vm2\.qemu_kvm_windows_10.*Win10.*.vm3.qemu_kvm_ubuntu.*Ubuntu.*")
        self.assertEqual(test_object.params["vms_vm1"], "vm1")
        self.assertEqual(test_object.params["vms_vm2"], "vm2")
        self.assertEqual(test_object.params["vms_vm3"], "vm3")
        self.assertEqual(test_object.params["os_variant_vm1"], "centos")
        self.assertEqual(test_object.params["os_variant_vm2"], "win10")
        self.assertEqual(test_object.params["os_variant_vm3"], "ubuntu")
        self.assertEqual(test_object.params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")
        self.assertNotIn("only", test_object.params)
        self.assertNotIn("only_vm1", test_object.params)
        self.assertNotIn("only_vm2", test_object.params)
        self.assertNotIn("only_vm3", test_object.params)

        test_object = TestGraph.parse_composite_objects("net1", "nets", "localhost",
                                                        self.config["vm_strs"], unique=True)
        self.assertRegex(test_object.params["name"], r"nets\.localhost\.net1")

        test_object = TestGraph.parse_composite_objects("net1", "nets", "no remotehost\nonly localhost\n",
                                                        self.config["vm_strs"], unique=True)
        self.assertRegex(test_object.params["name"], r"nets\.localhost\.net1")

        # some workers only support certain vm variants
        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_composite_objects("net5", "nets", "", {"vm1": "only CentOS\n"})
        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_composite_objects("net5", "nets", "", {"vm1": "no Fedora\n"})
        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_composite_objects("net5", "nets", "", {"vm2": "only Win7\n"})
        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_composite_objects("net5", "nets", "", {"vm2": "no Win10\n"})

    def test_parse_composite_objects_net_and_cluster(self):
        """Test for a correctly parsed cluster net object from empty joined vm string restrictions."""
        test_object = TestGraph.parse_composite_objects("cluster1.net6", "nets", "", self.config["vm_strs"], unique=True)
        self.assertRegex(test_object.params["name"], r"vm1\.qemu_kvm_centos.*CentOS.*vm2\.qemu_kvm_windows_10.*Win10.*.vm3.qemu_kvm_ubuntu.*Ubuntu.*")
        self.assertEqual(test_object.params["vms_vm1"], "vm1")
        self.assertEqual(test_object.params["vms_vm2"], "vm2")
        self.assertEqual(test_object.params["vms_vm3"], "vm3")
        self.assertEqual(test_object.params["os_variant_vm1"], "centos")
        self.assertEqual(test_object.params["os_variant_vm2"], "win10")
        self.assertEqual(test_object.params["os_variant_vm3"], "ubuntu")
        self.assertEqual(test_object.params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")
        self.assertNotIn("only", test_object.params)
        self.assertNotIn("only_vm1", test_object.params)
        self.assertNotIn("only_vm2", test_object.params)
        self.assertNotIn("only_vm3", test_object.params)
        # some workers only support certain vm variants

        test_object = TestGraph.parse_composite_objects("net6", "nets", "cluster1",
                                                        self.config["vm_strs"], unique=True)
        self.assertRegex(test_object.params["name"], r"nets\.cluster1\.net6")

        test_object = TestGraph.parse_composite_objects("net6", "nets", "no cluster1\nonly cluster2\n",
                                                        self.config["vm_strs"], unique=True)
        self.assertRegex(test_object.params["name"], r"nets\.cluster2\.net6")

        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_composite_objects("net9", "nets", "cluster2", {"vm1": "only Fedora\n"})
        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_composite_objects("net9", "nets", "cluster2", {"vm1": "no CentOS\n"})
        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_composite_objects("net9", "nets", "cluster2", {"vm2": "only Win10\n"})
        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_composite_objects("net9", "nets", "cluster2", {"vm2": "no Win7\n"})

    def test_parse_composite_objects_net_unrestricted(self):
        """Test for a correctly parsed net object from empty joined vm string restrictions."""
        test_objects = TestGraph.parse_composite_objects("net1", "nets", "")
        # TODO: bug in the Cartesian parser, they must be 6!
        self.assertEqual(len(test_objects), 4)
        for i, test_object in enumerate(test_objects):
            self.assertEqual(test_object.dict_index, i)

    def test_parse_suffix_objects_vms(self):
        """Test for correctly parsed vm objects of all suffices."""
        self.config["vm_strs"] = {"vm1": "", "vm2": "", "vm3": ""}
        test_objects = TestGraph.parse_suffix_objects("vms", self.config["vm_strs"], self.config["param_dict"])
        vms = [o for o in test_objects if o.key == "vms"]
        self.assertEqual(len(test_objects), len(vms))
        self.assertEqual(len(vms), 6)
        vms_vm1 = [vm for vm in vms if vm.long_suffix == "vm1"]
        self.assertEqual(len(vms_vm1), 2)
        self.assertEqual(vms_vm1[0].suffix, vms_vm1[1].suffix)
        self.assertEqual(vms_vm1[0].long_suffix, vms_vm1[1].long_suffix)
        self.assertNotEqual(vms_vm1[0].id, vms_vm1[1].id)
        self.assertEqual(len([vm for vm in vms if vm.long_suffix == "vm2"]), 2)
        self.assertEqual(len([vm for vm in vms if vm.long_suffix == "vm3"]), 2)

    def test_parse_suffix_objects_nets_flat(self):
        """Test for correctly parsed net objects of all suffices."""
        self.config["net_strs"] = {"net1": "", "net2": ""}
        test_objects = TestGraph.parse_suffix_objects("nets", self.config["net_strs"], self.config["param_dict"], flat=True)
        nets = [o for o in test_objects if o.key == "nets"]
        self.assertEqual(len(test_objects), len(nets))
        self.assertEqual(len(nets), 2)
        self.assertEqual(nets[0].suffix, "net1")
        self.assertEqual(nets[0].long_suffix, "net1")
        self.assertEqual(nets[1].suffix, "net2")
        self.assertEqual(nets[1].long_suffix, "net2")

    def test_parse_object_from_vms(self):
        """Test for a correctly parsed net composite object from already parsed vm component objects."""
        vms = []
        for vm_name, vm_restriction in self.config["vm_strs"].items():
            vms += TestGraph.parse_composite_objects(vm_name, "vms", vm_restriction)
        net = TestGraph.parse_object_from_objects("net1", "nets", vms)
        self.assertEqual(net.components, vms)
        for vm in vms:
            self.assertEqual(vm.composites, [net])
            # besides object composition we should expect the joined component variants
            self.assertIn(vm.component_form, net.params["name"])
            # each joined component variant must be traceable back to the component object id
            self.assertNotIn("object_id", net.params)
            self.assertEqual(vm.id, net.params[f"object_id_{vm.suffix}"])
            # each joined component variant must inform about supported vms via workaround restrictions
            self.assertEqual("only " + vm.component_form + "\n", net.restrs[vm.suffix])

    def test_parse_components_for_vm(self):
        """Test for correctly parsed image components with unflattened vm."""
        flat_vm = TestGraph.parse_flat_objects("vm1", "vms", "CentOS", unique=True)
        test_objects = TestGraph.parse_components_for_object(flat_vm, "vms", unflatten=True)
        vms = [o for o in test_objects if o.key == "vms"]
        images = [o for o in test_objects if o.key == "images"]
        self.assertEqual(len(test_objects), len(vms) + len(images))
        self.assertEqual(len(vms), 2)
        vms_vm1 = [vm for vm in vms if vm.long_suffix == "vm1"]
        self.assertEqual(len(vms_vm1), 2)
        self.assertEqual(vms_vm1[0].suffix, vms_vm1[1].suffix)
        self.assertEqual(vms_vm1[0].long_suffix, vms_vm1[1].long_suffix)
        self.assertNotEqual(vms_vm1[0].id, vms_vm1[1].id)
        self.assertEqual(len([image for image in images if image.long_suffix == "image1_vm1"]), 1)

    def test_parse_components_for_net(self):
        """Test for correctly parsed vm components with unflattened net."""
        flat_net = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        test_objects = TestGraph.parse_components_for_object(flat_net, "nets", unflatten=True)
        nets = [o for o in test_objects if o.key == "nets"]
        self.assertEqual(len(nets), 8)
        # TODO: typically we should test for some of this in the net1 object variants cases above but due to limitation of the Cartesian parser and lack of
        # such functionality, the multi-variant nets are generated at this stage and therefore tested here
        def assertVariant(test_object, name, vm1_os, vm2_os, vm3_os):
            self.assertEqual(test_object.suffix, "net1")
            self.assertEqual(test_object.long_suffix, "net1")
            self.assertRegex(test_object.params["name"], name)
            self.assertEqual(test_object.params["os_variant_vm1"], vm1_os)
            self.assertEqual(test_object.params["os_variant_vm2"], vm2_os)
            self.assertEqual(test_object.params["os_variant_vm3"], vm3_os)
            self.assertEqual(test_object.params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")
        assertVariant(nets[0], r"vm1\.qemu_kvm_fedora.*qcow.*Fedora.*vm2\.qemu_kvm_windows_7.*qcow.*Win7.*.vm3.qemu_kvm_ubuntu.*qcow.*Ubuntu.*", "fedora", "win7", "ubuntu")
        assertVariant(nets[1], r"vm1\.qemu_kvm_fedora.*qcow.*Fedora.*vm2\.qemu_kvm_windows_7.*qcow.*Win7.*.vm3.qemu_kvm_kali.*qcow.*Kali.*", "fedora", "win7", "kl")
        assertVariant(nets[2], r"vm1\.qemu_kvm_fedora.*qcow.*Fedora.*vm2\.qemu_kvm_windows_10.*qcow.*Win10.*.vm3.qemu_kvm_ubuntu.*qcow.*Ubuntu.*", "fedora", "win10", "ubuntu")
        assertVariant(nets[3], r"vm1\.qemu_kvm_fedora.*qcow.*Fedora.*vm2\.qemu_kvm_windows_10.*qcow.*Win10.*.vm3.qemu_kvm_kali.*qcow.*Kali.*", "fedora", "win10", "kl")
        assertVariant(nets[4], r"vm1\.qemu_kvm_centos.*qcow.*CentOS.*vm2\.qemu_kvm_windows_7.*.qcow.*Win7.*vm3.qemu_kvm_ubuntu.*qcow.*Ubuntu.*", "centos", "win7", "ubuntu")
        assertVariant(nets[5], r"vm1\.qemu_kvm_centos.*qcow.*CentOS.*vm2\.qemu_kvm_windows_7.*qcow.*Win7.*.vm3.qemu_kvm_kali.*qcow.*Kali.*", "centos", "win7", "kl")
        assertVariant(nets[6], r"vm1\.qemu_kvm_centos.*qcow.*CentOS.*vm2\.qemu_kvm_windows_10.*qcow.*Win10.*.vm3.qemu_kvm_ubuntu.*qcow.*Ubuntu.*", "centos", "win10", "ubuntu")
        assertVariant(nets[7], r"vm1\.qemu_kvm_centos.*qcow.*CentOS.*vm2\.qemu_kvm_windows_10.*qcow.*Win10.*.vm3.qemu_kvm_kali.*qcow.*Kali.*", "centos", "win10", "kl")

    def test_parse_components_for_net_restricted(self):
        """Test for correctly parsed restricted vm components with unflattened net."""
        flat_net = TestGraph.parse_flat_objects("net1", "nets", params={"only_vm1": "CentOS"}, unique=True)
        test_objects = TestGraph.parse_components_for_object(flat_net, "nets", restriction="qcow2", unflatten=True)
        nets = [o for o in test_objects if o.key == "nets"]
        self.assertEqual(len(nets), 4)
        # TODO: typically we should test for some of this in the net1 object variants cases above but due to limitation of the Cartesian parser and lack of
        # such functionality, the multi-variant nets are generated at this stage and therefore tested here
        def assertVariant(test_object, name, vm1_os, vm2_os, vm3_os):
            self.assertEqual(test_object.suffix, "net1")
            self.assertEqual(test_object.long_suffix, "net1")
            self.assertRegex(test_object.params["name"], name)
            self.assertEqual(test_object.params["os_variant_vm1"], vm1_os)
            self.assertEqual(test_object.params["os_variant_vm2"], vm2_os)
            self.assertEqual(test_object.params["os_variant_vm3"], vm3_os)
            self.assertEqual(test_object.params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")
        assertVariant(nets[0], r"vm1\.qemu_kvm_centos.*CentOS.*vm2\.qemu_kvm_windows_7.*Win7.*.vm3.qemu_kvm_ubuntu.*Ubuntu.*",
                      "centos", "win7", "ubuntu")
        assertVariant(nets[1], r"vm1\.qemu_kvm_centos.*CentOS.*vm2\.qemu_kvm_windows_7.*Win7.*.vm3.qemu_kvm_kali.*Kali.*",
                      "centos", "win7", "kl")
        assertVariant(nets[2], r"vm1\.qemu_kvm_centos.*CentOS.*vm2\.qemu_kvm_windows_10.*Win10.*.vm3.qemu_kvm_ubuntu.*Ubuntu.*",
                      "centos", "win10", "ubuntu")
        assertVariant(nets[3], r"vm1\.qemu_kvm_centos.*CentOS.*vm2\.qemu_kvm_windows_10.*Win10.*.vm3.qemu_kvm_kali.*Kali.*",
                      "centos", "win10", "kl")

    def test_params(self):
        """Test for correctly parsed and regenerated test object parameters."""
        test_object = TestGraph.parse_composite_objects("net1", "nets", "", self.config["vm_strs"],
                                                        params=self.config["param_dict"], unique=True)
        regenerated_params = test_object.object_typed_params(test_object.recipe.get_params())
        self.assertEqual(len(regenerated_params.keys()), len(test_object.params.keys()),
                        "The parameters of a test object must be the same as its only parser dictionary")
        for key in regenerated_params.keys():
            self.assertEqual(regenerated_params[key], test_object.params[key],
                            "The values of key %s %s=%s must be the same" % (key, regenerated_params[key], test_object.params[key]))
        # the test object attributes are fully separated from its parameters
        self.assertNotIn("object_suffix", test_object.params)
        self.assertNotIn("object_type", test_object.params)
        self.assertNotIn("object_id", test_object.params)

    def test_restrs(self):
        """Test for correctly parsed and regenerated test object restrictions."""
        restr_params = {"only_vm1": "CentOS", "only_vm2": "Win10,Win7", "only_vm3": "", "only_else": "something"}
        restr_strs = self.config["vm_strs"]
        restr_strs.update({"vm2": "only Win10,Win7\n", "vm3": ""})
        test_objects = TestGraph.parse_flat_objects("net1", "nets", "", params=restr_params)
        self.assertEqual(len(test_objects), 1)
        # provide also the restriction parameters here to make sure they are filtered out
        test_objects += TestGraph.parse_composite_objects("net1", "nets", "", restr_strs, params=restr_params)
        self.assertEqual(len(test_objects), 1+4)
        for test_object in test_objects:
            self.assertNotIn("only_vm1", test_object.params)
            self.assertNotIn("only_vm2", test_object.params)
            self.assertNotIn("only_vm3", test_object.params)
            self.assertNotIn("only_else", test_object.params)
            self.assertIn("vm1", test_object.restrs)
            self.assertEqual(test_object.restrs["vm1"], "only CentOS\n")
            self.assertIn("vm2", test_object.restrs)
            self.assertEqual(test_object.restrs["vm2"], "only Win10,Win7\n")
            self.assertIn("vm3", test_object.restrs)
            self.assertEqual(test_object.restrs["vm3"], "")
            if test_objects.index(test_object) == 0:
                self.assertIn("else", test_object.restrs)
                self.assertEqual(test_object.restrs["else"], "only something\n")
            else:
                self.assertNotIn("else", test_object.restrs)

            test_object.recipe.parse_next_dict({"only_vm1": "qcow2"})
            test_object.recipe.parse_next_dict({"no_vm1": "qcow1"})
            test_object.regenerate_params()
            self.assertNotIn("only_vm1", test_object.params)
            self.assertNotIn("only_vm2", test_object.params)
            self.assertNotIn("only_vm3", test_object.params)
            self.assertNotIn("only_else", test_object.params)
            self.assertIn("vm1", test_object.restrs)
            self.assertEqual(test_object.restrs["vm1"], "only CentOS\nonly qcow2\nno qcow1\n")
            self.assertIn("vm2", test_object.restrs)
            self.assertEqual(test_object.restrs["vm2"], "only Win10,Win7\n")
            self.assertIn("vm3", test_object.restrs)
            self.assertEqual(test_object.restrs["vm3"], "")
            if test_objects.index(test_object) == 0:
                self.assertIn("else", test_object.restrs)
                self.assertEqual(test_object.restrs["else"], "only something\n")
            else:
                self.assertNotIn("else", test_object.restrs)

        # restrictions should only apply if object is already composed with others
        self.assertEqual(len(TestGraph.parse_flat_objects("net3", "nets", "", params=restr_params)), 1)
        # default component restrictions must further restrict config parameter restrictions
        self.assertEqual(len(TestGraph.parse_composite_objects("net3", "nets", "", restr_strs)), 4)
        # can also produce single vm nets with more permissive config parameter restrictions
        self.assertEqual(len(TestGraph.parse_composite_objects("net3", "nets", "", {"vm2": "only Win10\n"})), 1)
        # flat nodes are not fully composed yet to evaluate compatibility
        self.assertEqual(len(TestGraph.parse_flat_objects("net5", "nets", "", params=restr_params)), 1)
        # composite nodes may be incompatible from their default configuration
        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_composite_objects("net5", "nets", "", restr_strs)

    def test_sanity_in_graph(self):
        """Test generic usage and composition of test objects within a graph."""
        self.config["tests_str"] += "only tutorial1\n"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )

        test_objects = graph.get_objects(param_val="vm1", subset=graph.get_objects(param_val="net1"))
        for test_object in test_objects:
            self.assertIn(test_object.long_suffix, ["vm1", "net1"])
            object_num = len(graph.objects_index)
            graph.new_objects(test_object)
            self.assertEqual(len(graph.objects_index), object_num)


class CartesianNodeTest(Test):

    def setUp(self):
        self.config = {}
        self.config["param_dict"] = {"test_timeout": 100, "shared_pool": "/mnt/local/images/shared", "nets": "net1"}
        self.config["tests_str"] = "only normal\n"
        self.config["vm_strs"] = {"vm1": "only CentOS\n", "vm2": "only Win10\n", "vm3": "only Ubuntu\n"}

        self.prefix = ""

        self.loader = TestLoader(config=self.config, extra_params={})

        self.shared_pool = ":" + self.config["param_dict"]["shared_pool"]

        self.maxDiff = None

    def test_prefix_tree_contains(self):
        """Test that a prefix tree contains the right variants."""
        tree = PrefixTree()
        node1 = TestNode("1", None)
        node2 = TestNode("2", None)
        node3 = TestNode("3", None)
        node1._params_cache = {"name": "aaa.bbb.ccc"}
        node2._params_cache = {"name": "aaa.bbb.fff"}
        node3._params_cache = {"name": "eee.bbb.fff"}
        tree.insert(node1)
        tree.insert(node2)
        tree.insert(node3)

        self.assertTrue("aaa" in tree)
        self.assertTrue("aaa.bbb" in tree)
        self.assertTrue("bbb.ccc" in tree)
        self.assertTrue("bbb" in tree)
        self.assertTrue("bbb.fff" in tree)
        self.assertTrue("eee.bbb" in tree)
        self.assertTrue("ddd" not in tree)
        self.assertTrue("ccc.ddd" not in tree)
        self.assertTrue("aaa.ddd" not in tree)
        self.assertTrue("aaa.fff" not in tree)

    def test_prefix_tree_insert(self):
        """Test the right variants are produced when inserting a test node into the prefix tree."""
        tree = PrefixTree()
        node1 = TestNode("1", None)
        node2 = TestNode("2", None)
        node3 = TestNode("3", None)
        node1._params_cache = {"name": "aaa.bbb.ccc"}
        node2._params_cache = {"name": "aaa.bbb.fff"}
        node3._params_cache = {"name": "eee.bbb.fff"}
        tree.insert(node1)
        tree.insert(node2)
        tree.insert(node3)

        self.assertEqual(tree.variant_nodes.keys(), set(["aaa", "bbb", "ccc", "eee", "fff"]))
        self.assertEqual(len(tree.variant_nodes["aaa"]), 1)
        self.assertIn("bbb", tree.variant_nodes["aaa"][0].children)
        self.assertEqual(len(tree.variant_nodes["bbb"]), 2)
        self.assertEqual(len(tree.variant_nodes["bbb"][0].children), 2)
        self.assertIn("ccc", tree.variant_nodes["bbb"][0].children)
        self.assertIn("fff", tree.variant_nodes["bbb"][0].children)
        self.assertEqual(len(tree.variant_nodes["bbb"][1].children), 1)
        self.assertIn("fff", tree.variant_nodes["bbb"][1].children)
        self.assertNotIn(tree.variant_nodes["bbb"][1].children["fff"], tree.variant_nodes["bbb"][0].children)

    def test_prefix_tree_get(self):
        """Test the right test nodes are retrieved when looking up a composite variant."""
        tree = PrefixTree()
        node1 = TestNode("1", None)
        node2 = TestNode("2", None)
        node3 = TestNode("3", None)
        node1._params_cache = {"name": "aaa.bbb.ccc"}
        node2._params_cache = {"name": "aaa.bbb.fff"}
        node3._params_cache = {"name": "eee.bbb.fff"}
        tree.insert(node1)
        tree.insert(node2)
        tree.insert(node3)

        self.assertEqual(len(tree.get("aaa")), 2)
        self.assertIn(node1, tree.get("aaa"))
        self.assertIn(node2, tree.get("aaa"))
        self.assertEqual(len(tree.get("aaa.bbb")), 2)
        self.assertIn(node1, tree.get("aaa.bbb"))
        self.assertIn(node2, tree.get("aaa.bbb"))
        self.assertEqual(len(tree.get("bbb.ccc")), 1)
        self.assertIn(node1, tree.get("bbb.ccc"))

        self.assertEqual(len(tree.get("bbb")), 3)
        self.assertEqual(len(tree.get("bbb.fff")), 2)
        self.assertIn(node2, tree.get("bbb.fff"))
        self.assertIn(node3, tree.get("bbb.fff"))
        self.assertEqual(len(tree.get("eee.bbb")), 1)
        self.assertIn(node3, tree.get("bbb.fff"))
        self.assertEqual(len(tree.get("ddd")), 0)

        self.assertEqual(len(tree.get("ccc.ddd")), 0)
        self.assertEqual(len(tree.get("aaa.ddd")), 0)
        self.assertEqual(len(tree.get("aaa.fff")), 0)

    def test_edge_register(self):
        """Test the right test nodes are retrieved when from node's edge registers."""
        register = EdgeRegister()
        node1 = mock.MagicMock(id="1", bridged_form="key1")
        node2 = mock.MagicMock(id="2", bridged_form="key1")
        node3 = mock.MagicMock(id="3", bridged_form="key2")
        worker1 = mock.MagicMock(id="net1")
        worker2 = mock.MagicMock(id="net2")

        self.assertEqual(register.get_workers(node1), set())
        self.assertEqual(register.get_workers(node2), set())
        self.assertEqual(register.get_workers(node3), set())
        self.assertEqual(register.get_counters(node1), 0)
        self.assertEqual(register.get_counters(node2), 0)
        self.assertEqual(register.get_counters(node3), 0)

        register.register(node1, worker1)
        self.assertEqual(register.get_workers(node1), {worker1.id})
        self.assertEqual(register.get_counters(node1), 1)
        self.assertEqual(register.get_counters(node1, worker1), 1)
        self.assertEqual(register.get_counters(node1, worker2), 0)
        self.assertEqual(register.get_workers(node2), {worker1.id})
        self.assertEqual(register.get_counters(node2), 1)
        self.assertEqual(register.get_counters(node2, worker1), 1)
        self.assertEqual(register.get_counters(node2, worker2), 0)
        self.assertEqual(register.get_workers(node3), set())
        self.assertEqual(register.get_counters(node3), 0)
        self.assertEqual(register.get_counters(node3, worker1), 0)
        self.assertEqual(register.get_counters(node3, worker2), 0)
        self.assertEqual(register.get_workers(), {worker1.id})
        self.assertEqual(register.get_counters(worker=worker1), 1)
        self.assertEqual(register.get_counters(worker=worker2), 0)
        self.assertEqual(register.get_counters(), 1)

        register.register(node1, worker2)
        register.register(node2, worker2)
        register.register(node3, worker2)
        self.assertEqual(register.get_workers(node1), {worker1.id, worker2.id})
        self.assertEqual(register.get_counters(node1), 3)
        self.assertEqual(register.get_counters(node1, worker1), 1)
        self.assertEqual(register.get_counters(node1, worker2), 2)
        self.assertEqual(register.get_workers(node2), {worker1.id, worker2.id})
        self.assertEqual(register.get_counters(node2), 3)
        self.assertEqual(register.get_counters(node2, worker1), 1)
        self.assertEqual(register.get_counters(node2, worker2), 2)
        self.assertEqual(register.get_workers(node3), {worker2.id})
        self.assertEqual(register.get_counters(node3), 1)
        self.assertEqual(register.get_counters(node3, worker1), 0)
        self.assertEqual(register.get_counters(node3, worker2), 1)
        self.assertEqual(register.get_workers(), {worker1.id, worker2.id})
        self.assertEqual(register.get_counters(worker=worker1), 1)
        self.assertEqual(register.get_counters(worker=worker2), 3)
        self.assertEqual(register.get_counters(), 4)

    def test_parse_flat_nodes(self):
        """Test for a correctly parsed flat nodes."""
        test_node = TestGraph.parse_flat_nodes("normal..tutorial1", unique=True)
        self.assertRegex(test_node.params["name"], r"normal.*tutorial1.*")
        self.assertEqual(test_node.params["vms"], "vm1")

        test_node = TestGraph.parse_flat_nodes("only normal\nonly tutorial1", unique=True)
        self.assertRegex(test_node.params["name"], r"normal.*tutorial1.*")
        self.assertEqual(test_node.params["vms"], "vm1")

        test_node = TestGraph.parse_flat_nodes("only leaves..tutorial2\nno files\n", unique=True)
        self.assertRegex(test_node.params["name"], r"leaves.*tutorial2.names.*")
        self.assertEqual(test_node.params["vms"], "vm1")

    def test_parse_node_from_object(self):
        """Test for a correctly parsed node from an already parsed net object."""
        flat_net = TestGraph.parse_net_from_object_restrs("net1", self.config["vm_strs"])
        test_objects = TestGraph.parse_components_for_object(flat_net, "nets", params=self.config["param_dict"], unflatten=True)
        nets = [o for o in test_objects if o.key == "nets"]
        self.assertEqual(len(nets), 1)
        net = nets[0]
        node = TestGraph.parse_node_from_object(net, "all..tutorial_get..explicit_noop", params=self.config["param_dict"])
        self.assertEqual(node.objects[0], net)
        self.assertIn(net.params["name"], node.params["name"])
        self.assertEqual(node.params["nets"], net.params["nets"])
        self.assertEqual(node.params["vms_vm1"], net.params["vms_vm1"])
        self.assertEqual(node.params["vms_vm2"], net.params["vms_vm2"])
        self.assertEqual(node.params["vms_vm3"], net.params["vms_vm3"])
        self.assertEqual(node.params["os_variant_vm1"], net.params["os_variant_vm1"])
        self.assertEqual(node.params["os_variant_vm2"], net.params["os_variant_vm2"])
        self.assertEqual(node.params["os_variant_vm3"], net.params["os_variant_vm3"])
        self.assertEqual(node.params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")

    def test_parse_node_from_object_invalid_object_type(self):
        """Test correctly parsed node is not possible from an already parsed vm object."""
        flat_net = TestGraph.parse_net_from_object_restrs("net1", {"vm1": self.config["vm_strs"]["vm1"]})
        test_objects = TestGraph.parse_components_for_object(flat_net, "nets", params=self.config["param_dict"], unflatten=True)
        vms = [o for o in test_objects if o.key == "vms"]
        self.assertEqual(len(vms), 1)
        vm = vms[0]
        with self.assertRaises(ValueError):
            TestGraph.parse_node_from_object(vm, params=self.config["param_dict"])

    def test_parse_node_from_object_invalid_object_mix(self):
        """Test correctly parsed node is not possible from incompatible vm variants."""
        self.config["vm_strs"]["vm2"] = "only Win7\n"
        flat_net = TestGraph.parse_net_from_object_restrs("net1", self.config["vm_strs"])
        test_objects = TestGraph.parse_components_for_object(flat_net, "nets", params=self.config["param_dict"], unflatten=True)
        nets = [o for o in test_objects if o.key == "nets"]
        self.assertEqual(len(nets), 1)
        net = nets[0]
        self.assertIn("Win7", net.restrs["vm2"])
        self.assertIn("Win7", net.params["name"])
        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_node_from_object(flat_net, "all..tutorial1")
        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_node_from_object(net, "all..tutorial3.remote.object.control.decorator.util", params=self.config["param_dict"])
        net.restrs["vm2"] = "no Win10\n"
        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_node_from_object(net, "all..tutorial3.remote.object.control.decorator.util", params=self.config["param_dict"])

    def test_get_and_parse_objects_for_node_and_object_flat(self):
        """Test parsing and retrieval of objects for a flat pair of test node and object."""
        graph = TestGraph()
        flat_node = TestGraph.parse_flat_nodes("normal..tutorial1", unique=True)
        flat_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        self.assertNotIn("only_vm1", flat_object.params)
        flat_object.restrs["vm1"] = "only CentOS\n"
        flat_object.params["nets_some_key"] = "some_value"
        get_objects, parse_objects = graph.get_and_parse_objects_for_node_and_object(flat_node, flat_object)
        self.assertEqual(len(get_objects), 0)
        test_objects = parse_objects

        self.assertEqual(len(test_objects), 1)
        self.assertEqual(test_objects[0].suffix, "net1")
        #self.assertIn("CentOS", test_objects[0].params[""])
        self.assertIn("CentOS", test_objects[0].id)
        self.assertEqual(len(test_objects[0].components), 1)
        self.assertIn("CentOS", test_objects[0].components[0].id)
        self.assertEqual(len(test_objects[0].components[0].components), 1)
        self.assertEqual(test_objects[0].components[0].components[0].long_suffix, "image1_vm1")
        self.assertEqual(test_objects[0].params["nets_some_key"], flat_object.params["nets_some_key"])
        self.assertEqual(test_objects[0].params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")

    def test_get_and_parse_objects_for_node_and_object_full(self):
        """Test default parsing and retrieval of objects for a flat test node and full test object."""
        graph = TestGraph()
        flat_node = TestGraph.parse_flat_nodes("normal..tutorial1", unique=True)
        full_object = TestGraph.parse_composite_objects("net1", "nets", "", self.config["vm_strs"], unique=True)
        # TODO: limitation in the Cartesian config
        self.assertIn("CentOS", full_object.restrs["vm1"])
        full_object.params["nets_some_key"] = "some_value"
        get_objects, parse_objects = graph.get_and_parse_objects_for_node_and_object(flat_node, full_object)
        self.assertEqual(len(get_objects), 0)
        test_objects = parse_objects

        self.assertEqual(len(test_objects), 1)

        self.assertEqual(test_objects[0].suffix, "net1")
        self.assertIn("CentOS", test_objects[0].id)
        self.assertEqual(len(test_objects[0].components), 1)
        self.assertIn("CentOS", test_objects[0].components[0].id)
        self.assertEqual(len(test_objects[0].components[0].components), 1)
        self.assertEqual(test_objects[0].components[0].components[0].long_suffix, "image1_vm1")
        self.assertEqual(test_objects[0].params["nets_some_key"], full_object.params["nets_some_key"])
        self.assertEqual(test_objects[0].params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")

    def test_parse_nodes_from_flat_node_and_object(self):
        """Test for correctly parsed composite nodes from a flat node and object."""
        flat_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)

        flat_object.params["vms"] = "vm1"
        test_objects = TestGraph.parse_components_for_object(flat_object, "nets", unflatten=True)
        nets = [o for o in test_objects if o.key == "nets"]
        self.assertEqual(len(nets), 2)
        graph = TestGraph()
        graph.new_objects(test_objects)

        flat_nodes = graph.parse_flat_nodes("normal..tutorial1,normal..tutorial2")
        self.assertEqual(len(flat_nodes), 2)
        for flat_node in flat_nodes:
            nodes = graph.parse_nodes_from_flat_node_and_object(flat_node, flat_object)
            self.assertEqual(len(nodes), 2)
            for node in nodes:
                self.assertIn(node.objects[0], nets)
                self.assertEqual(len(node.objects[0].components), 1)
                self.assertEqual(len(node.objects[0].components[0].components), 1)
                self.assertEqual(node.params["nets"], "net1")
                self.assertEqual(node.params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")

        flat_node = graph.parse_flat_nodes("normal..tutorial3", unique=True)
        nodes = graph.parse_nodes_from_flat_node_and_object(flat_node, flat_object)
        self.assertEqual(len(nodes), 4)
        for node in nodes:
            self.assertEqual(node.params["nets"], "net1")
            self.assertEqual(node.params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")

    def test_get_and_parse_nodes_from_flat_node_and_object_unique(self):
        """Test for a unique parsed and reused graph retrievable composite node from a flat node and object."""
        self.config["tests_str"] += "only tutorial1,tutorial2\n"
        graph = TestGraph()
        graph.restrs.update(self.config["vm_strs"])

        flat_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)

        flat_nodes = TestGraph.parse_flat_nodes(self.config["tests_str"])
        self.assertEqual(len(flat_nodes), 2)
        self.assertIn("tutorial1", flat_nodes[0].id)
        self.assertIn("tutorial2", flat_nodes[1].id)
        for flat_node in flat_nodes:
            # make sure to parse just one object variant of each node, only test reusability
            flat_node.update_restrs(self.config["vm_strs"])
            get_nodes, parse_nodes = graph.get_and_parse_nodes_from_flat_node_and_object(flat_node, flat_object,
                                                                                         params=self.config["param_dict"])
            self.assertEqual(len(parse_nodes), 1)
            self.assertIn(flat_node.setless_form, parse_nodes[0].id)
            self.assertIn(flat_object.component_form, parse_nodes[0].id)
            self.assertEqual(len(get_nodes), 0)

            graph.new_nodes(parse_nodes)

        for flat_node in flat_nodes:
            get_nodes, parse_nodes = graph.get_and_parse_nodes_from_flat_node_and_object(flat_node, flat_object,
                                                                                         params=self.config["param_dict"])
            self.assertEqual(len(parse_nodes), 0)
            self.assertEqual(len(get_nodes), 1)
            self.assertIn(flat_node.setless_form, get_nodes[0].id)
            self.assertIn(flat_object.component_form, get_nodes[0].id)

        graph.restrs["vm1"] = ""
        flat_nodes = TestGraph.parse_flat_nodes(self.config["tests_str"])
        for flat_node in flat_nodes:
            get_nodes, parse_nodes = graph.get_and_parse_nodes_from_flat_node_and_object(flat_node, flat_object,
                                                                                         params=self.config["param_dict"])
            self.assertEqual(len(parse_nodes), 1)
            self.assertEqual(len(get_nodes), 1)
            self.assertIn(flat_node.setless_form, parse_nodes[0].id)
            self.assertIn(flat_object.component_form, parse_nodes[0].id)
            self.assertIn(flat_node.setless_form, get_nodes[0].id)
            self.assertIn(flat_object.component_form, get_nodes[0].id)

    def test_get_and_parse_nodes_from_flat_node_and_object_multiple(self):
        """Test for correctly parsed and reused graph retrievable composite nodes from a flat node and object."""
        self.config["tests_str"] += "only tutorial1,tutorial2\n"
        graph = TestGraph()

        flat_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)

        flat_nodes = TestGraph.parse_flat_nodes(self.config["tests_str"])
        self.assertEqual(len(flat_nodes), 2)
        self.assertIn("tutorial1", flat_nodes[0].id)
        self.assertIn("tutorial2", flat_nodes[1].id)
        for flat_node in flat_nodes:
            get_nodes, parse_nodes = graph.get_and_parse_nodes_from_flat_node_and_object(flat_node, flat_object,
                                                                                         params=self.config["param_dict"])
            self.assertEqual(len(parse_nodes), 2)
            self.assertIn(flat_node.setless_form, parse_nodes[0].id)
            self.assertIn(flat_node.setless_form, parse_nodes[1].id)
            self.assertIn(flat_object.component_form, parse_nodes[0].id)
            self.assertIn(flat_object.component_form, parse_nodes[1].id)
            self.assertEqual(len(get_nodes), 0)

            graph.new_nodes(parse_nodes)

        for flat_node in flat_nodes:
            get_nodes, parse_nodes = graph.get_and_parse_nodes_from_flat_node_and_object(flat_node, flat_object,
                                                                                         params=self.config["param_dict"])
            self.assertEqual(len(parse_nodes), 0)
            self.assertEqual(len(get_nodes), 2)
            self.assertIn(flat_node.setless_form, get_nodes[0].id)
            self.assertIn(flat_node.setless_form, get_nodes[1].id)
            self.assertIn(flat_object.component_form, get_nodes[0].id)
            self.assertIn(flat_object.component_form, get_nodes[1].id)

    def test_parse_composite_nodes(self):
        """Test for correctly parsed composite nodes from graph retrievable test objects."""
        flat_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)

        flat_object.params["vms"] = "vm1"
        test_objects = TestGraph.parse_components_for_object(flat_object, "nets", unflatten=True)
        nets = [o for o in test_objects if o.key == "nets"]
        self.assertEqual(len(nets), 2)
        graph = TestGraph()
        graph.new_objects(test_objects)

        nodes = graph.parse_composite_nodes("normal..tutorial1,normal..tutorial2", flat_object)
        self.assertEqual(len(nodes), 4)
        self.assertIn(nodes[0].objects[0], nets)
        self.assertEqual(len(nodes[0].objects[0].components), 1)
        self.assertEqual(len(nodes[0].objects[0].components[0].components), 1)
        self.assertIn(nodes[1].objects[0], nets)
        self.assertIn(nodes[2].objects[0], nets)
        self.assertIn(nodes[3].objects[0], nets)
        for node in nodes:
            self.assertRegex(node.params["name"], r"normal.*tutorial.*")
            self.assertEqual(node.params["nets"], "net1")
            self.assertEqual(node.params["vms"], "vm1")
            self.assertEqual(node.params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")

        nodes = graph.parse_composite_nodes("only normal\nonly tutorial3", flat_object)
        self.assertEqual(len(nodes), 4)
        for node in nodes:
            self.assertRegex(node.params["name"], r"normal.*tutorial3.*")
            self.assertEqual(node.params["nets"], "net1")
            self.assertEqual(node.params["vms"], "vm1 vm2")
            self.assertEqual(node.params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")

        nodes = graph.parse_composite_nodes("only leaves..tutorial2\nno files\n", flat_object)
        self.assertEqual(len(nodes), 2)
        for node in nodes:
            self.assertRegex(node.params["name"], r"leaves.*tutorial2.names.*")
            self.assertEqual(node.params["nets"], "net1")
            self.assertEqual(node.params["vms"], "vm1")
            self.assertEqual(node.params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")

    def test_parse_composite_nodes_compatibility_complete(self):
        """Test for correctly parsed test nodes from compatible graph retrievable test objects."""
        self.config["tests_str"] = "only all\nonly tutorial3\n"

        flat_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)

        flat_object.params["vms"] = "vm1 vm2"
        test_objects = TestGraph.parse_components_for_object(flat_object, "nets", unflatten=True)
        nets = [o for o in test_objects if o.key == "nets"]
        self.assertEqual(len(nets), 4)
        graph = TestGraph()
        graph.new_objects(test_objects)

        self.assertEqual(nets, [o for o in test_objects if o.key == "nets" if "vm1." in o.params["name"] and "vm2." in o.params["name"]])
        nets = list(reversed([o for o in test_objects if o.key == "nets"]))
        self.assertRegex(nets[0].params["name"], "qemu_kvm_centos.+qemu_kvm_windows_10")
        self.assertRegex(nets[1].params["name"], "qemu_kvm_centos.+qemu_kvm_windows_7")
        self.assertRegex(nets[2].params["name"], "qemu_kvm_fedora.+qemu_kvm_windows_10")
        self.assertRegex(nets[3].params["name"], "qemu_kvm_fedora.+qemu_kvm_windows_7")
        nodes = graph.parse_composite_nodes(self.config["tests_str"], flat_object, params=self.config["param_dict"])
        self.assertEqual(len(nodes), 20)
        for i in range(0, 4):
            self.assertIn("no_remote", nodes[i].params["name"])
            self.assertNotIn("only_vm1", nodes[i].params)
            self.assertNotIn("only_vm2", nodes[i].params)
            self.assertIn(nets[i].params["name"], nodes[i].params["name"])
        for i in range(4, 20):
            self.assertIn("remote", nodes[i].params["name"])
            self.assertNotIn("only_vm1", nodes[i].params)
            self.assertNotIn("only_vm2", nodes[i].params)
            self.assertIn("qemu_kvm_centos", nodes[i].restrs["vm1"])
            self.assertIn("qemu_kvm_windows_10", nodes[i].restrs["vm2"])
            self.assertIn(nets[0].params["name"], nodes[i].params["name"])

    def test_parse_composite_nodes_compatibility_separate(self):
        """Test that no restriction leaks across separately restricted variants."""
        self.config["tests_str"] = "only all\nonly tutorial3.remote.object.control.decorator.util,tutorial_gui.client_noop\n"

        flat_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)

        flat_object.params["vms"] = "vm1 vm2"
        test_objects = TestGraph.parse_components_for_object(flat_object, "nets", unflatten=True)
        nets = [o for o in test_objects if o.key == "nets"]
        self.assertEqual(len(nets), 4)
        graph = TestGraph()
        graph.new_objects(test_objects)

        self.assertEqual(nets, [o for o in test_objects if o.key == "nets" if "vm1." in o.params["name"] and "vm2." in o.params["name"]])
        nets = list(reversed([o for o in test_objects if o.key == "nets"]))
        self.assertRegex(nets[0].params["name"], "qemu_kvm_centos.+qemu_kvm_windows_10")
        self.assertRegex(nets[1].params["name"], "qemu_kvm_centos.+qemu_kvm_windows_7")
        self.assertRegex(nets[2].params["name"], "qemu_kvm_fedora.+qemu_kvm_windows_10")
        self.assertRegex(nets[3].params["name"], "qemu_kvm_fedora.+qemu_kvm_windows_7")
        nodes = graph.parse_composite_nodes(self.config["tests_str"], flat_object, params=self.config["param_dict"])
        self.assertEqual(len(nodes), 5)
        self.assertIn("remote", nodes[0].params["name"])
        self.assertNotIn("only_vm1", nodes[0].params)
        self.assertNotIn("only_vm2", nodes[0].params)
        self.assertIn("qemu_kvm_centos", nodes[0].restrs["vm1"])
        self.assertIn("qemu_kvm_windows_10", nodes[0].restrs["vm2"])
        self.assertIn(nets[0].params["name"], nodes[0].params["name"])
        for i in range(1, 5):
            self.assertIn("client_noop", nodes[i].params["name"])
            self.assertNotIn("only_vm1", nodes[i].params)
            self.assertNotIn("only_vm2", nodes[i].params)
            self.assertIn(nets[i-1].params["name"], nodes[i].params["name"])

    def test_get_and_parse_composite_nodes(self):
        """Test for correctly parsed and reused graph retrievable composite nodes."""
        self.config["tests_str"] += "only tutorial1,tutorial2\n"

        flat_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)

        flat_object.params["vms"] = "vm1"
        test_objects = TestGraph.parse_components_for_object(flat_object, "nets", unflatten=True)
        nets = [o for o in test_objects if o.key == "nets"]
        self.assertEqual(len(nets), 2)
        graph = TestGraph()
        graph.new_objects(test_objects)

        get_nodes, parse_nodes = graph.get_and_parse_composite_nodes(self.config["tests_str"], flat_object,
                                                                     params=self.config["param_dict"])
        self.assertEqual(len(parse_nodes), 4)
        self.assertEqual(len([p for p in parse_nodes if "tutorial1" in p.id]), 2)
        self.assertEqual(len([p for p in parse_nodes if "tutorial2" in p.id]), 2)
        self.assertEqual(len(get_nodes), 0)

        reused_nodes = [parse_nodes[0], parse_nodes[-1]]
        graph.new_nodes(reused_nodes)
        get_nodes, parse_nodes = graph.get_and_parse_composite_nodes(self.config["tests_str"], flat_object,
                                                                     params=self.config["param_dict"])
        self.assertEqual(len(parse_nodes), 2)
        self.assertEqual(len([p for p in parse_nodes if "tutorial1" in p.id]), 1)
        self.assertEqual(len([p for p in parse_nodes if "tutorial2" in p.id]), 1)
        self.assertEqual(len(get_nodes), 2)
        self.assertEqual(len([p for p in parse_nodes if "tutorial1" in p.id]), 1)
        self.assertEqual(len([p for p in parse_nodes if "tutorial2" in p.id]), 1)
        self.assertEqual(get_nodes, reused_nodes)

    def test_get_and_parse_nodes_from_composite_node_and_object_unique(self):
        """Test for a unique parsed and reused graph retrievable composite node from a composite node and object."""
        graph = TestGraph()
        nodes, objects = TestGraph.parse_object_nodes(None, "normal..tutorial1", prefix=self.prefix,
                                                      object_restrs=self.config["vm_strs"],
                                                      params=self.config["param_dict"])
        self.assertEqual(len(nodes), 1)
        full_node = nodes[0]
        self.assertEqual(len(objects), 3)

        self.assertEqual(len([o for o in objects if o.key == "nets"]), 1)
        full_net = [o for o in objects if o.key == "nets"][0]
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_net)
        self.assertEqual(len(get_nodes), 0)
        self.assertEqual(len(parse_nodes), 0)

        self.assertEqual(len([o for o in objects if o.key == "vms"]), 1)
        full_vm = [o for o in objects if o.key == "vms"][0]
        self.assertEqual(full_vm.params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_vm)
        self.assertEqual(len(get_nodes), 0)
        self.assertEqual(len(parse_nodes), 1)
        new_node = parse_nodes[0]
        self.assertEqual(new_node.prefix, "1a1")
        self.assertEqual(new_node.params["nets"], "net1")
        self.assertEqual(new_node.params["cdrom_cd_rip"], "/mnt/local/isos/avocado_rip.iso")
        graph.new_nodes(parse_nodes)
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_vm)
        self.assertEqual(len(get_nodes), 1)
        self.assertEqual(len(parse_nodes), 0)
        self.assertEqual(get_nodes[0], new_node)

        self.assertEqual(len([o for o in objects if o.key == "images"]), 1)
        full_image = [o for o in objects if o.key == "images"][0]
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_image)
        self.assertEqual(len(get_nodes), 0)
        self.assertEqual(len(parse_nodes), 0)

    def test_get_and_parse_nodes_from_composite_node_and_object_multiple(self):
        """Test for multiple parsed and reused graph retrievable composite nodes from a composite node and object."""
        graph = TestGraph()
        nodes, objects = TestGraph.parse_object_nodes(None, "leaves..tutorial_get..implicit_both", prefix=self.prefix,
                                                      object_restrs=self.config["vm_strs"],
                                                      params=self.config["param_dict"])
        self.assertEqual(len(nodes), 1)
        full_node = nodes[0]
        self.assertEqual(len(objects), 7, "We need 3 images, 3 vms, and 1 net")

        self.assertEqual(len([o for o in objects if o.key == "nets"]), 1)
        full_net = [o for o in objects if o.key == "nets"][0]
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_net)
        self.assertEqual(len(get_nodes), 0)
        self.assertEqual(len(parse_nodes), 0)

        self.assertEqual(len([o for o in objects if o.key == "vms"]), 3)
        for full_vm in [o for o in objects if o.key == "vms"]:
            get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_vm)
            self.assertEqual(len(get_nodes), 0)
            self.assertEqual(len(parse_nodes), 0)

        self.assertEqual(len([o for o in objects if o.key == "images"]), 3)
        full_image = [o for o in objects if o.key == "images" and o.long_suffix == "image1_vm2"][0]
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_image)
        self.assertEqual(len(get_nodes), 0)
        self.assertEqual(len(parse_nodes), 2)
        self.assertEqual([n.prefix for n in parse_nodes], ["1a1", "1a2"])
        graph.new_nodes(parse_nodes)
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_image)
        self.assertEqual(len(get_nodes), 2)
        self.assertEqual(len(parse_nodes), 0)

    def test_get_and_parse_nodes_from_composite_node_and_object_unique_multiobject(self):
        """Test for a multi-object restricted composite node from a composite node and object."""
        self.config["vm_strs"]["vm1"] = "only CentOS, Fedora\n"
        graph = TestGraph()
        nodes, objects = TestGraph.parse_object_nodes(None, "all..tutorial_get..explicit_noop", prefix=self.prefix,
                                                      object_restrs=self.config["vm_strs"],
                                                      params=self.config["param_dict"])
        self.assertEqual(len(nodes), 1)
        full_node = nodes[0]
        self.assertEqual(len(objects), 7, "We need 3 images, 3 vms, and 1 net")
        full_image = [o for o in objects if o.key == "images" and o.long_suffix == "image1_vm2"][0]

        # not truly reusable parent due to a different auxiliary vm variant
        self.config["vm_strs"]["vm1"] = "only Fedora\n"
        reused_nodes, _ = TestGraph.parse_object_nodes(None, "all..tutorial_gui..client_noop", prefix=self.prefix,
                                                       object_restrs=self.config["vm_strs"],
                                                       params=self.config["param_dict"])
        self.assertEqual(len(reused_nodes), 1)
        graph.new_nodes(reused_nodes)

        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_image)
        self.assertEqual(len(get_nodes), 0)
        self.assertEqual(len(parse_nodes), 1)
        new_node = parse_nodes[0]
        self.assertIn("CentOS", new_node.setless_form)
        self.assertNotIn("Fedora", new_node.setless_form)
        graph.new_nodes(parse_nodes)
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_image)
        self.assertEqual(len(get_nodes), 1)
        self.assertEqual(len(parse_nodes), 0)
        self.assertEqual(get_nodes[0], new_node)

    def test_get_and_parse_nodes_from_composite_node_and_object_unique_with_cloning(self):
        """Test for multiple cloned parsed and reused graph retrievable composite nodes from a composite node and object."""
        graph = TestGraph()
        nodes, objects = TestGraph.parse_object_nodes(None, "leaves..tutorial_get..implicit_both", prefix=self.prefix,
                                                      object_restrs=self.config["vm_strs"],
                                                      params=self.config["param_dict"])
        self.assertEqual(len(nodes), 1)
        full_node = nodes[0]
        self.assertEqual(len(objects), 7, "We need 3 images, 3 vms, and 1 net")
        full_image = [o for o in objects if o.key == "images" and o.long_suffix == "image1_vm2"][0]

        final_node = graph.parse_composite_nodes("leaves..tutorial_finale", full_node.objects[0], unique=True)

        # if unique dependency is cloned at some later point preserve default unique node reuse
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(final_node, full_image)
        self.assertEqual(len(get_nodes), 0)
        self.assertEqual(len(parse_nodes), 1)
        graph.new_nodes(full_node)
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(final_node, full_image)
        self.assertEqual(len(get_nodes), 1)
        self.assertEqual(len(parse_nodes), 0)
        self.assertEqual(get_nodes, [full_node])

        # clones are reusable from retrieving the original clone sources
        _, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_image)
        clones = graph.parse_cloned_branches_for_node_and_object(full_node, full_image, parse_nodes)
        graph.new_nodes(clones)
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(final_node, full_image)
        self.assertEqual(len(get_nodes), 2)
        self.assertEqual(len(parse_nodes), 0)
        self.assertEqual(get_nodes, clones)

    def test_get_and_parse_nodes_from_composite_node_and_object_with_leaves(self):
        """Test that leaf nodes are properly reused when parsed as dependencies for node and object."""
        graph = TestGraph()
        nodes, objects = TestGraph.parse_object_nodes(None, "all..tutorial_get.explicit_clicked", prefix=self.prefix,
                                                      object_restrs=self.config["vm_strs"],
                                                      params=self.config["param_dict"])
        self.assertEqual(len(nodes), 1)
        full_node = nodes[0]
        self.assertEqual(len(objects), 1+3+3)

        self.assertEqual(len([o for o in objects if o.key == "nets"]), 1)
        full_net = [o for o in objects if o.key == "nets"][0]
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_net)
        self.assertEqual(len(get_nodes), 0)
        self.assertEqual(len(parse_nodes), 0)

        self.assertEqual(len([o for o in objects if o.key == "vms"]), 3)
        for full_vm in [o for o in objects if o.key == "vms"]:
            get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_vm)
            self.assertEqual(len(get_nodes), 0)
            self.assertEqual(len(parse_nodes), 0)

        self.assertEqual(len([o for o in objects if o.key == "images"]), 3)

        # standard handling for vm1 as in other tests
        full_image1 = [o for o in objects if o.key == "images" and "vm1" in o.long_suffix][0]
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_image1)
        self.assertEqual(len(get_nodes), 0)
        self.assertEqual(len(parse_nodes), 1)
        graph.new_nodes(parse_nodes)
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_image1)
        self.assertEqual(len(get_nodes), 1)
        self.assertEqual(len(parse_nodes), 0)

        # most important part regarding reusability
        full_image2 = [o for o in objects if o.key == "images" and "vm2" in o.long_suffix][0]
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_image2)
        self.assertEqual(len(get_nodes), 0)
        self.assertEqual(len(parse_nodes), 1)
        # we are adding a leaf node that should be reused as the setup of this node
        leaf_nodes = graph.parse_composite_nodes("leaves..tutorial_gui.client_clicked", full_net)
        graph.new_nodes(leaf_nodes)
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_image2)
        self.assertEqual(len(get_nodes), 1)
        self.assertEqual(len(parse_nodes), 0)
        self.assertEqual(get_nodes, leaf_nodes)

        # no nodes for permanent object vm3
        full_image3 = [o for o in objects if o.key == "images" and "vm3" in o.long_suffix][0]
        get_nodes, parse_nodes = graph.get_and_parse_nodes_from_composite_node_and_object(full_node, full_image3)
        self.assertEqual(len(get_nodes), 0)
        self.assertEqual(len(parse_nodes), 0)

    def test_params(self):
        """Test for correctly parsed test node parameters."""
        flat_net = TestGraph.parse_flat_objects("net1", "nets", params={"only_vm1": "CentOS"}, unique=True)
        graph = TestGraph()
        test_node = graph.parse_composite_nodes("normal..tutorial1", flat_net, unique=True)

        dict_generator = test_node.recipe.get_parser().get_dicts()
        dict1 = dict_generator.__next__()
        # parser of test objects must contain exactly one dictionary
        self.assertRaises(StopIteration, dict_generator.__next__)
        self.assertEqual(len(dict1.keys()), len(test_node.params.keys()), "The parameters of a test node must be the same as its only parser dictionary")
        for key in dict1.keys():
            self.assertEqual(dict1[key], test_node.params[key], "The values of key %s %s=%s must be the same" % (key, dict1[key], test_node.params[key]))
        # all VT attributes must be initialized
        self.assertEqual(test_node.uri, test_node.params["name"])

    def test_restrs(self):
        """Test for correctly parsed and regenerated test node restrictions."""
        restr_params = {"only_vm1": "CentOS", "only_vm2": "Win10,Win7", "only_vm3": ""}
        restr_strs = self.config["vm_strs"]
        restr_strs.update({"vm2": "only Win10,Win7\n", "vm3": ""})
        flat_net = TestGraph.parse_flat_objects("net1", "nets", params=restr_params, unique=True)
        graph = TestGraph()

        test_nodes = TestGraph.parse_flat_nodes("all..explicit_clicked", params=restr_params)
        test_nodes += graph.parse_composite_nodes("all..explicit_clicked", flat_net)
        for test_node in test_nodes:
            self.assertNotIn("only_vm1", test_node.params)
            self.assertNotIn("only_vm2", test_node.params)
            self.assertNotIn("only_vm3", test_node.params)
            if test_nodes.index(test_node) == 0:
                # restricted vms apply to the flat node during its own parsing
                self.assertIn("vm1", test_node.restrs)
                self.assertEqual(test_node.restrs["vm1"], "only CentOS\n")
                self.assertIn("vm2", test_node.restrs)
                self.assertEqual(test_node.restrs["vm2"], "only Win10,Win7\n")
                self.assertIn("vm3", test_node.restrs)
                self.assertEqual(test_node.restrs["vm3"], "")
            else:
                # supported vms don't affect needed vms of the full node
                self.assertIn("vm1", test_node.restrs)
                self.assertEqual(test_node.restrs["vm1"], "only qemu_kvm_centos\n")
                self.assertNotIn("vm2", test_node.restrs)
                self.assertNotIn("vm3", test_node.restrs)

            test_node.recipe.parse_next_dict({"only_vm1": "qcow2"})
            test_node.recipe.parse_next_dict({"no_vm1": "qcow1"})
            test_node.regenerate_params()
            self.assertNotIn("only_vm1", test_node.params)
            self.assertNotIn("only_vm2", test_node.params)
            self.assertNotIn("only_vm3", test_node.params)
            self.assertIn("vm1", test_node.restrs)
            if test_nodes.index(test_node) == 0:
                # new filter parameter overwrites the old only so CentOS is now repeated
                self.assertEqual(test_node.restrs["vm1"], "only CentOS\nonly qcow2\nno qcow1\n")
                self.assertIn("vm2", test_node.restrs)
                self.assertEqual(test_node.restrs["vm2"], "only Win10,Win7\n")
                self.assertIn("vm3", test_node.restrs)
                self.assertEqual(test_node.restrs["vm3"], "")
            else:
                # overwriting the only_vm1 parameter adds the restrictions as extra
                self.assertEqual(test_node.restrs["vm1"], "only qemu_kvm_centos\nonly qcow2\nno qcow1\n")
                self.assertNotIn("vm2", test_node.restrs)
                self.assertNotIn("vm3", test_node.restrs)

    def test_shared_workers(self):
        """Test for correctly shared workers across bridged nodes."""
        flat_net1 = TestGraph.parse_flat_objects("net1", "nets", params={"only_vm1": "CentOS"}, unique=True)
        flat_net2 = TestGraph.parse_flat_objects("net2", "nets", params={"only_vm1": "CentOS"}, unique=True)
        graph = TestGraph()
        test_node1 = graph.parse_composite_nodes("normal..tutorial1", flat_net1, unique=True)
        test_node2 = graph.parse_composite_nodes("normal..tutorial1", flat_net2, unique=True)
        test_node1.bridge_with_node(test_node2)

        self.assertEqual(test_node1.finished_worker, None)
        self.assertEqual(test_node1.finished_worker, test_node2.finished_worker)
        self.assertEqual(test_node1.shared_finished_workers, set())
        self.assertEqual(test_node1.shared_finished_workers, test_node2.shared_finished_workers)

        worker1 = mock.MagicMock(id="net1", params={"nets_host": "1"})
        test_node1.finished_worker = worker1
        self.assertEqual(test_node1.finished_worker, worker1)
        self.assertEqual(test_node2.finished_worker, None)
        self.assertEqual(test_node1.shared_finished_workers, {worker1})
        self.assertEqual(test_node1.shared_finished_workers, test_node2.shared_finished_workers)
        worker2 = mock.MagicMock(id="net2", params={"nets_host": "2"})
        test_node2.finished_worker = worker2
        self.assertEqual(test_node1.finished_worker, worker1)
        self.assertEqual(test_node2.finished_worker, worker2)
        self.assertEqual(test_node1.shared_finished_workers, {worker1, worker2})
        self.assertEqual(test_node2.shared_finished_workers, {worker1, worker2})

        # validate trivial behavior for flat nodes
        test_node3 = TestGraph.parse_flat_nodes("normal..tutorial1", unique=True)
        self.assertEqual(test_node3.finished_worker, None)
        self.assertEqual(test_node3.shared_finished_workers, set())
        test_node3.finished_worker = worker1
        self.assertEqual(test_node3.finished_worker, worker1)
        self.assertEqual(test_node3.shared_finished_workers, {test_node3.finished_worker})
        test_node3.finished_worker = worker2
        self.assertEqual(test_node3.finished_worker, worker2)
        self.assertEqual(test_node3.shared_finished_workers, {test_node3.finished_worker})

    def test_shared_involved_workers(self):
        """Test for correctly shared incompatible workers across flat parent node."""
        flat_node = TestGraph.parse_flat_nodes("leaves..explicit_noop", unique=True)

        flat_net1 = TestGraph.parse_flat_objects("net1", "nets",
                                                 params={"only_vm1": "CentOS", "only_vm2": "Win10", "only_vm3": "Ubuntu"},
                                                 unique=True)
        flat_net2 = TestGraph.parse_flat_objects("net2", "nets",
                                                 params={"only_vm1": "CentOS", "only_vm2": "Win10", "only_vm3": "Ubuntu"},
                                                 unique=True)
        graph = TestGraph()
        test_node1 = graph.parse_composite_nodes("leaves..explicit_noop", flat_net1, unique=True)
        test_node2 = graph.parse_composite_nodes("leaves..explicit_noop", flat_net2, unique=True)
        test_node1.bridge_with_node(test_node2)

        test_node1.descend_from_node(flat_node, flat_net1)
        test_node2.descend_from_node(flat_node, flat_net2)

        self.assertEqual(flat_node.shared_involved_workers, set())
        self.assertEqual(test_node1.shared_involved_workers, set())
        self.assertEqual(test_node2.shared_involved_workers, set())

        worker1 = TestWorker(flat_net1)
        worker2 = TestWorker(flat_net2)
        swarm = TestSwarm("localhost", [worker1, worker2])
        TestSwarm.run_swarms = {swarm.id: swarm}

        picked_node1 = flat_node.pick_child(worker1)
        self.assertEqual(flat_node.shared_involved_workers, set())
        self.assertEqual(test_node1.shared_involved_workers, {worker1})
        self.assertEqual(test_node2.shared_involved_workers, {worker1})
        picked_node2 = flat_node.pick_child(worker2)
        self.assertEqual(flat_node.shared_involved_workers, set())
        self.assertEqual(test_node1.shared_involved_workers, {worker1, worker2})
        self.assertEqual(test_node2.shared_involved_workers, {worker1, worker2})
        self.assertEqual({picked_node1, picked_node2}, {test_node1, test_node2})

        picked_parent1 = test_node1.pick_parent(worker1)
        self.assertEqual(flat_node.shared_involved_workers, {worker1})
        picked_parent2 = test_node2.pick_parent(worker2)
        self.assertEqual(flat_node.shared_involved_workers, {worker1, worker2})
        self.assertEqual(picked_parent1, picked_parent2)
        self.assertEqual(picked_parent1, flat_node)

    def test_shared_results_and_worker_ids(self):
        """Test for correctly shared results and result-based worker ID-s across bridged nodes."""
        flat_net1 = TestGraph.parse_flat_objects("net1", "nets", params={"only_vm1": "CentOS"}, unique=True)
        flat_net2 = TestGraph.parse_flat_objects("net2", "nets", params={"only_vm1": "CentOS"}, unique=True)
        swarm = TestSwarm("localhost", [TestWorker(flat_net1), TestWorker(flat_net2)])
        TestSwarm.run_swarms = {swarm.id: swarm}
        graph = TestGraph()
        test_node1 = graph.parse_composite_nodes("normal..tutorial1", flat_net1, unique=True)
        test_node2 = graph.parse_composite_nodes("normal..tutorial1", flat_net2, unique=True)
        test_node1.bridge_with_node(test_node2)

        self.assertEqual(test_node1.results, [])
        self.assertEqual(test_node1.results, test_node2.results)
        self.assertEqual(test_node1.shared_results, [])
        self.assertEqual(test_node1.shared_results, test_node2.shared_results)

        node2_results = [{"name": "tutorial1.net2", "status": "PASS"}]
        test_node2.results += node2_results
        self.assertEqual(test_node1.results, [])
        self.assertEqual(test_node1.shared_results, node2_results)
        self.assertEqual(test_node2.shared_results, node2_results)
        self.assertEqual(test_node1.shared_result_worker_ids, {"net2"})
        self.assertEqual(test_node2.shared_result_worker_ids, test_node1.shared_result_worker_ids)

        node1_results = [{"name": "tutorial1.net1", "status": "FAIL"}]
        test_node1.results += node1_results
        self.assertEqual(test_node2.results, node2_results)
        self.assertEqual(test_node1.shared_results, node1_results + node2_results)
        self.assertEqual(test_node2.shared_results, node2_results + node1_results)
        # only net2 succeeded and can provide any tutorial1 setup
        self.assertEqual(test_node1.shared_result_worker_ids, {"net2"})
        self.assertEqual(test_node2.shared_result_worker_ids, test_node1.shared_result_worker_ids)

        node1_extra_results = [{"name": "tutorial1.net1", "status": "PASS"}]
        test_node1.results += node1_extra_results
        self.assertEqual(test_node2.results, node2_results)
        self.assertEqual(test_node1.shared_results, node1_results + node1_extra_results + node2_results)
        self.assertEqual(test_node2.shared_results, node2_results + node1_results + node1_extra_results)
        # now net1 succeeded too and can provide any tutorial1 setup
        self.assertEqual(test_node1.shared_result_worker_ids, {"net1", "net2"})
        self.assertEqual(test_node2.shared_result_worker_ids, test_node1.shared_result_worker_ids)

    def test_shared_results_filter(self):
        """Test for correctly shared but filtered results across bridged nodes."""
        flat_net1 = TestGraph.parse_flat_objects("cluster1.net6", "nets", params={"only_vm1": "CentOS"}, unique=True)
        flat_net2 = TestGraph.parse_flat_objects("cluster2.net6", "nets", params={"only_vm1": "CentOS"}, unique=True)
        worker1, worker2 = TestWorker(flat_net1), TestWorker(flat_net2)
        swarm1, swarm2 = TestSwarm("localhost", [worker1]), TestSwarm("localhost", [worker2])
        TestSwarm.run_swarms = {swarm1.id: swarm1, swarm2.id: swarm2}
        graph = TestGraph()
        test_node1 = graph.parse_composite_nodes("normal..tutorial1", flat_net1, unique=True, params={"pool_scope": "own swarm shared"})
        test_node2 = graph.parse_composite_nodes("normal..tutorial1", flat_net2, unique=True, params={"pool_scope": "own swarm shared"})
        test_node1.started_worker = worker1
        test_node2.started_worker = worker2
        test_node1.bridge_with_node(test_node2)

        self.assertEqual(test_node1.results, [])
        self.assertEqual(test_node1.results, test_node2.results)
        self.assertEqual(test_node1.shared_filtered_results, [])
        self.assertEqual(test_node1.shared_filtered_results, test_node2.shared_filtered_results)

        node2_results = [{"name": "tutorial1.cluster2.net6", "status": "PASS"}]
        test_node2.results += node2_results
        self.assertEqual(test_node1.results, [])
        self.assertEqual(test_node1.shared_results, node2_results)
        self.assertEqual(test_node2.shared_results, node2_results)
        self.assertEqual(test_node1.shared_filtered_results, [])
        self.assertEqual(test_node2.shared_filtered_results, node2_results)

        node1_results = [{"name": "tutorial1.cluster1.net6", "status": "FAIL"}]
        test_node1.results += node1_results
        self.assertEqual(test_node2.results, node2_results)
        self.assertEqual(test_node1.shared_results, node1_results + node2_results)
        self.assertEqual(test_node2.shared_results, node2_results + node1_results)
        self.assertEqual(test_node1.shared_filtered_results, node1_results)
        self.assertEqual(test_node2.shared_filtered_results, node2_results)

    def test_setless_form(self):
        """Test the general use and purpose of the node setless form."""
        flat_net = TestGraph.parse_flat_objects("net1", "nets",
                                                params={"only_vm1": "CentOS", "only_vm2": "Win10", "only_vm3": "Ubuntu"},
                                                unique=True)

        graph = TestGraph()
        nodes = [*graph.parse_composite_nodes("leaves..tutorial_get.explicit_clicked", flat_net),
                 *graph.parse_composite_nodes("all..tutorial_get.explicit_clicked", flat_net)]
        self.assertEqual(len(nodes), 2)
        self.assertNotEqual(nodes[0].params["name"], nodes[1].params["name"])
        self.assertEqual(nodes[0].setless_form, nodes[1].setless_form)

    def test_bridged_form(self):
        """Test the general use and purpose of the node bridged form."""
        restriction_params = {"only_vm1": "CentOS", "only_vm2": "Win10", "only_vm3": "Ubuntu"}
        flat_net1 = TestGraph.parse_flat_objects("net1", "nets", params=restriction_params, unique=True)
        flat_net2 = TestGraph.parse_flat_objects("net2", "nets", params=restriction_params, unique=True)

        graph = TestGraph()
        nodes = [*graph.parse_composite_nodes("all..tutorial_get.explicit_clicked", flat_net1),
                 *graph.parse_composite_nodes("all..tutorial_get.explicit_clicked", flat_net2)]
        self.assertEqual(len(nodes), 2)
        self.assertNotEqual(nodes[0].params["name"], nodes[1].params["name"])
        self.assertEqual(nodes[0].bridged_form, nodes[1].bridged_form)

    def test_sanity_in_graph(self):
        """Test generic usage and composition."""
        self.config["tests_str"] += "only tutorial1\n"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )

        test_node = graph.get_nodes(param_val="tutorial1",
                                       subset=graph.get_nodes(param_val="net1"), unique=True)
        self.assertIn("1", test_node.prefix)
        self.assertIn("1-net1.vm1", test_node.long_prefix)

    def test_is_unrolled(self):
        """Test that a flat test node is considered unrolled under the right circumstances."""
        graph = TestGraph()
        flat_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        flat_node = TestGraph.parse_flat_nodes("normal..tutorial1", unique=True)
        self.assertFalse(flat_node.is_unrolled(TestWorker(flat_object)))

        composite_nodes = graph.parse_composite_nodes("normal..tutorial1", flat_object)
        self.assertEqual(len(composite_nodes), 2)
        for node in composite_nodes:
            node.descend_from_node(flat_node, flat_object)
        self.assertTrue(flat_node.is_unrolled(TestWorker(flat_object)))
        more_flat_objects = TestGraph.parse_flat_objects("net2", "nets")
        self.assertEqual(len(more_flat_objects), 1)
        # flat node should not be unrolled for other workers
        self.assertFalse(flat_node.is_unrolled(TestWorker(more_flat_objects[0])))
        # flat node should be unrolled for any (at least one arbitrary) worker
        self.assertTrue(flat_node.is_unrolled())

        flat_node = TestGraph.parse_flat_nodes("normal..tutorial1", unique=True)
        more_composite_nodes = graph.parse_composite_nodes("normal..tutorial2", flat_object)
        self.assertGreater(len(more_composite_nodes), 0)
        more_composite_nodes[0].descend_from_node(flat_node, flat_object)
        self.assertFalse(flat_node.is_unrolled(TestWorker(flat_object)))

        with self.assertRaises(RuntimeError):
            composite_nodes[0].is_unrolled(TestWorker(flat_object))

        flat_node = TestGraph.parse_flat_nodes("normal..tutorial1", unique=True)
        flat_node.params["shared_root"] = "yes"
        self.assertTrue(flat_node.is_unrolled(TestWorker(flat_object)))

        flat_node = TestGraph.parse_flat_nodes("normal..tutorial1", unique=True)
        incompatible_worker = TestWorker(flat_object)
        flat_node.incompatible_workers.add(flat_object.long_suffix)
        self.assertTrue(flat_node.is_unrolled(incompatible_worker))

    def test_is_ready(self):
        """Test that a test node is setup/cleanup ready under the right circumstances."""
        flat_net = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        flat_net.update_restrs(self.config["vm_strs"])
        worker = TestWorker(flat_net)
        full_components = TestGraph.parse_components_for_object(flat_net, "nets", "", unflatten=True)
        full_net = full_components[-1]

        node = TestGraph.parse_node_from_object(full_net, "normal..tutorial1")
        node1 = TestGraph.parse_node_from_object(full_net, "normal..tutorial1", prefix="1")
        node2 = TestGraph.parse_node_from_object(full_net, "normal..tutorial2", prefix="2")
        node.descend_from_node(node1, flat_net)
        node.descend_from_node(node2, flat_net)
        node1.descend_from_node(node, flat_net)
        node2.descend_from_node(node, flat_net)

        # not ready by default
        self.assertFalse(node.is_setup_ready(worker))
        self.assertFalse(node.is_cleanup_ready(worker))

        # not ready if more setup/cleanup is not provided (nodes dropped)
        node.drop_parent(node1, worker)
        node.drop_child(node2, worker)
        self.assertFalse(node.is_setup_ready(worker))
        self.assertFalse(node.is_cleanup_ready(worker))

        # ready if all setup/cleanup is provided (nodes dropped)
        node.drop_parent(node2, worker)
        node.drop_child(node1, worker)
        self.assertTrue(node.is_setup_ready(worker))
        self.assertTrue(node.is_cleanup_ready(worker))

        # nodes might not yet be parsed for another worker (independent decision)
        flat_net = TestGraph.parse_flat_objects("net2", "nets", unique=True)
        worker2 = TestWorker(flat_net)
        self.assertTrue(node.is_setup_ready(worker2))
        self.assertTrue(node.is_cleanup_ready(worker2))

        # a flat setup/cleanup node can affect the second worker
        node3 = TestGraph.parse_flat_nodes("normal..tutorial2", unique=True)
        node.descend_from_node(node3, flat_net)
        node3.descend_from_node(node, flat_net)
        self.assertFalse(node.is_setup_ready(worker))
        self.assertFalse(node.is_cleanup_ready(worker))
        self.assertFalse(node.is_setup_ready(worker2))
        self.assertFalse(node.is_cleanup_ready(worker2))
        node.drop_parent(node3, worker)
        node.drop_child(node3, worker)
        self.assertTrue(node.is_setup_ready(worker))
        self.assertTrue(node.is_cleanup_ready(worker))
        self.assertFalse(node.is_setup_ready(worker2))
        self.assertFalse(node.is_cleanup_ready(worker2))
        node.drop_parent(node3, worker2)
        node.drop_child(node3, worker2)
        self.assertTrue(node.is_setup_ready(worker))
        self.assertTrue(node.is_cleanup_ready(worker))
        self.assertTrue(node.is_setup_ready(worker2))
        self.assertTrue(node.is_cleanup_ready(worker2))

    def test_is_started_or_finished(self):
        """Test that a test node is eagerly to fully started or finished in different scopes."""
        nets = " ".join(param.all_suffixes_by_restriction("only cluster1,cluster2\nno cluster2.net8,net9\n"))
        test_workers = TestGraph.parse_workers({"nets": nets, "only_vm1": "CentOS"})
        full_nodes = []
        for worker in test_workers:
            new_node = TestGraph().parse_composite_nodes("normal..tutorial1", worker.net, prefix="1", unique=True)
            for bridge in full_nodes:
                new_node.bridge_with_node(bridge)
            # cluster1.net8 will not participate (not an involved worker)
            if test_workers.index(worker) != 2:
                new_node._picked_by_setup_nodes.register(mock.MagicMock(), worker)
            full_nodes += [new_node]

        # most eager threshold is satisfied with at least one worker
        full_nodes[0].started_worker = test_workers[0]
        for node in full_nodes:
            for worker in test_workers:
                self.assertTrue(node.is_started(worker, 1))
                self.assertFalse(node.is_started(worker, 2))
                self.assertFalse(node.is_started(worker, -1))
        full_nodes[1].finished_worker = test_workers[1]
        for node in full_nodes:
            for worker in test_workers:
                self.assertTrue(node.is_finished(worker, 1))
                self.assertFalse(node.is_finished(worker, 2))
                self.assertFalse(node.is_finished(worker, -1))

        # less eager threshold is satisfied with more workers
        full_nodes[1].started_worker = test_workers[1]
        for node in full_nodes:
            for worker in test_workers:
                self.assertTrue(node.is_started(worker, 1))
                self.assertTrue(node.is_started(worker, 2))
                self.assertFalse(node.is_started(worker, -1))
        full_nodes[0].finished_worker = test_workers[0]
        for node in full_nodes:
            for worker in test_workers:
                self.assertTrue(node.is_finished(worker, 1))
                self.assertTrue(node.is_finished(worker, 2))
                self.assertFalse(node.is_finished(worker, -1))

        # fullest threshold is satisfied only with all involved workers
        for node, worker in zip(full_nodes, test_workers):
            if test_workers.index(worker) != 2:
                node.started_worker = worker
        for node in full_nodes:
            for worker in test_workers:
                self.assertTrue(node.is_started(worker, 1))
                self.assertTrue(node.is_started(worker, 2))
                self.assertTrue(node.is_started(worker, -1))
        for node, worker in zip(full_nodes, test_workers):
            if test_workers.index(worker) != 2:
                node.finished_worker = worker
        for node in full_nodes:
            for worker in test_workers:
                self.assertTrue(node.is_finished(worker, 1))
                self.assertTrue(node.is_finished(worker, 2))
                self.assertTrue(node.is_finished(worker, -1))

    def test_is_started_or_finished_filter(self):
        """Test that a test node is eagerly to fully started or finished in filtered scopes."""
        nets = " ".join(param.all_suffixes_by_restriction("only cluster1,cluster2.net6,cluster2.net7\n"))
        test_workers = TestGraph.parse_workers({"nets": nets, "only_vm1": "CentOS"})
        full_nodes = []
        for worker in test_workers:
            new_node = TestGraph().parse_composite_nodes("normal..tutorial1", worker.net,
                                                         prefix="1", params={"pool_scope": "own swarm shared"},
                                                         unique=True)
            for bridge in full_nodes:
                new_node.bridge_with_node(bridge)
            # cluster1.net8 will not participate (not an involved worker)
            if test_workers.index(worker) != 2:
                new_node._picked_by_setup_nodes.register(mock.MagicMock(), worker)
            full_nodes += [new_node]

        # most eager threshold is satisfied with at least one worker per swarm
        full_nodes[0].started_worker = test_workers[0]
        for node, worker in zip(full_nodes, test_workers):
            started_for_swarm = test_workers.index(worker) < 4
            self.assertEqual(node.is_started(worker, 1), started_for_swarm)
            self.assertFalse(node.is_started(worker, 2))
            self.assertFalse(node.is_started(worker, -1))
        full_nodes[1].finished_worker = test_workers[1]
        for node, worker in zip(full_nodes, test_workers):
            finished_for_swarm = test_workers.index(worker) < 4
            self.assertEqual(node.is_finished(worker, 1), finished_for_swarm)
            self.assertFalse(node.is_finished(worker, 2))
            self.assertFalse(node.is_finished(worker, -1))

        # less eager threshold is satisfied with more workers per swarm
        full_nodes[1].started_worker = test_workers[1]
        for node in full_nodes:
            for worker in test_workers:
                started_for_swarm = test_workers.index(worker) < 4
                self.assertEqual(node.is_started(worker, 1), started_for_swarm)
                self.assertEqual(node.is_started(worker, 2), started_for_swarm)
                self.assertFalse(node.is_started(worker, -1))
        full_nodes[0].finished_worker = test_workers[0]
        for node in full_nodes:
            for worker in test_workers:
                finished_for_swarm = test_workers.index(worker) < 4
                self.assertEqual(node.is_finished(worker, 1), finished_for_swarm)
                self.assertEqual(node.is_finished(worker, 2), finished_for_swarm)
                self.assertFalse(node.is_finished(worker, -1))

        # fullest threshold is satisfied only with all workers of the swarm
        for node, worker in zip(full_nodes, test_workers):
            if test_workers.index(worker) != 2 and test_workers.index(worker) < 4:
                node.started_worker = worker
        for node in full_nodes:
            for worker in test_workers:
                started_for_swarm = test_workers.index(worker) < 4
                self.assertEqual(node.is_started(worker, 1), started_for_swarm)
                self.assertEqual(node.is_started(worker, 2), started_for_swarm)
                self.assertEqual(node.is_started(worker, -1), started_for_swarm)
        for node, worker in zip(full_nodes, test_workers):
            if test_workers.index(worker) != 2 and test_workers.index(worker) < 4:
                node.finished_worker = worker
        for node in full_nodes:
            for worker in test_workers:
                finished_for_swarm = test_workers.index(worker) < 4
                self.assertEqual(node.is_finished(worker, 1), finished_for_swarm)
                self.assertEqual(node.is_finished(worker, 2), finished_for_swarm)
                self.assertEqual(node.is_finished(worker, -1), finished_for_swarm)

    def test_is_started_or_finished_flat(self):
        """Test that a flat node is always started and finished with any threshold."""
        nets = " ".join(param.all_suffixes_by_restriction("only cluster1,cluster2\nno cluster2.net8,net9\n"))
        test_workers = TestGraph.parse_workers({"nets": nets})
        flat_node = TestGraph.parse_flat_nodes("normal..tutorial1", unique=True)
        for worker in test_workers:
            flat_node.started_worker = worker
            self.assertTrue(flat_node.is_flat())
            self.assertFalse(flat_node.is_started(worker, 1))
            self.assertFalse(flat_node.is_started(worker, 2))
            self.assertFalse(flat_node.is_started(worker, -1))
            flat_node.finished_worker = worker
            self.assertTrue(flat_node.is_flat())
            self.assertTrue(flat_node.is_finished(worker, 1))
            self.assertTrue(flat_node.is_finished(worker, 2))
            self.assertTrue(flat_node.is_finished(worker, -1))

    def test_should_parse(self):
        """Test expectations on the default decision policy of whether to parse or skip a test node."""
        flat_node = TestGraph.parse_flat_nodes("normal..tutorial1", unique=True)

        flat_net1 = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        worker1 = TestWorker(flat_net1)
        flat_net2 = TestGraph.parse_flat_objects("net2", "nets", params={"only_vm1": ""}, unique=True)
        worker2 = TestWorker(flat_net2)
        swarm = TestSwarm("localhost", [worker1, worker2])
        TestSwarm.run_swarms = {swarm.id: swarm}
        flat_node._picked_by_setup_nodes.register(mock.MagicMock("some_setup", bridged_form="setup"), worker1)
        flat_node._picked_by_setup_nodes.register(mock.MagicMock("some_setup", bridged_form="setup"), worker2)

        # parse flat node for first worker
        self.assertTrue(flat_node.should_parse(worker1))

        graph = TestGraph()
        _, children = graph.parse_branches_for_node_and_object(flat_node, flat_net1)
        self.assertEqual(len(children), 2)

        # parse flat node for any worker if only unrolled but not cleaned by first worker
        self.assertTrue(flat_node.should_parse(worker1))
        self.assertTrue(flat_node.should_parse(worker2))

        # parse if one child dropped by a worker (not yet cleanup ready)
        flat_node.drop_child(children[0], worker1)
        self.assertTrue(flat_node.should_parse(worker1))
        self.assertTrue(flat_node.should_parse(worker2))
        # do not parse parse if both children dropped by first worker (cleanup ready for at least one worker)
        flat_node.drop_child(children[1], worker1)
        self.assertFalse(flat_node.should_parse(worker1))
        self.assertFalse(flat_node.should_parse(worker2))

        # parse if cleanup ready for a worker with restrictions (cannot guarantee all full nodes parsed)
        worker1.net.update_restrs({"vm1": "only CentOS\n"})
        self.assertTrue(flat_node.should_parse(worker1))
        self.assertTrue(flat_node.should_parse(worker2))

        # parse if checked for worker that wasn't previously involved
        flat_net3 = TestGraph.parse_flat_objects("net3", "nets", params={"only_vm1": ""}, unique=True)
        worker3 = TestWorker(flat_net3)
        TestSwarm.run_swarms["localhost"].workers += [worker3]
        self.assertTrue(flat_node.should_parse(worker3))

    @mock.patch('virttest.cartgraph.worker.remote.wait_for_login', mock.MagicMock())
    @mock.patch('virttest.cartgraph.node.door', DummyStateControl)
    def test_default_run_decision(self):
        """Test expectations on the default decision policy of whether to run or skip a test node."""
        self.config["tests_str"] += "only tutorial1\n"
        params = {"nets": "net1 net2"}
        graph = TestGraph.parse_object_trees(
            restriction=self.config["tests_str"],
            object_restrs=self.config["vm_strs"],
            params=params,
        )

        worker1 = graph.workers["net1"]
        worker2 = graph.workers["net2"]

        test_node1 = graph.get_nodes(param_val="tutorial1.+net1", unique=True)
        test_node2 = graph.get_nodes(param_val="tutorial1.+net2", unique=True)
        # should run a leaf test node visited for the first time
        self.assertTrue(test_node1.default_run_decision(worker1))
        self.assertTrue(test_node2.default_run_decision(worker2))
        # should never run a leaf test node meant for other worker
        with self.assertRaises(RuntimeError):
            test_node1.default_run_decision(worker2)
        with self.assertRaises(RuntimeError):
            test_node2.default_run_decision(worker1)
        # should not run already visited leaf test node
        test_node1.results += [{"name": "tutorial1.net1", "status": "PASS"}]
        self.assertFalse(test_node1.default_run_decision(worker1))
        # should not run already visited bridged test node
        test_node1.results = []
        test_node2.results += [{"name": "tutorial1.net2", "status": "PASS"}]
        self.assertIn(test_node2, test_node1.bridged_nodes)
        self.assertEqual(test_node1.shared_results, test_node2.results)
        self.assertFalse(test_node1.default_run_decision(worker1))
        # should run leaf if more reruns are needed
        test_node1.should_rerun = lambda _: True
        self.assertTrue(test_node1.default_run_decision(worker1))

        test_node1 = graph.get_nodes(param_val="install.+net1", unique=True)
        test_node2 = graph.get_nodes(param_val="install.+net2", unique=True)
        # run decisions involving scans require a started worker which is typically assumed
        test_node1.started_worker = worker1
        # should never run an internal test node meant for other worker
        with self.assertRaises(RuntimeError):
            test_node1.default_run_decision(worker2)
        with self.assertRaises(RuntimeError):
            test_node2.default_run_decision(worker1)
        # should run an internal test node without available setup
        DummyStateControl.asserted_states["check"] = {"install": {self.shared_pool: False}}
        test_node1.params["nets_host"], test_node1.params["nets_gateway"] = "1", ""
        self.assertTrue(test_node1.default_run_decision(worker1))
        # should not run an internal test node with available setup
        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        self.assertFalse(test_node1.default_run_decision(worker1))
        # should not run already visited internal test node by the same worker
        test_node1.finished_worker = worker1
        test_node1.results += [{"name": "install.net1", "status": "PASS"}]
        self.assertFalse(test_node1.default_run_decision(worker1))
        # should not run an internal test node if needed reruns and setup from past runs
        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        test_node1.should_rerun = lambda _: True
        test_node1.finished_worker = None
        test_node1.results = []
        self.assertFalse(test_node1.default_run_decision(worker1))
        # should run an internal test node if needed reruns and setup from current runs
        test_node1.should_rerun = lambda _: True
        test_node1.finished_worker = None
        test_node1.results = [{"name": "install.net2", "status": "PASS"}]
        self.assertTrue(test_node1.default_run_decision(worker1))

    @mock.patch('virttest.cartgraph.worker.remote.wait_for_login', mock.MagicMock())
    def test_default_clean_decision(self):
        """Test expectations on the default decision policy of whether to clean or not a test node."""
        self.config["tests_str"] = "only leaves\n"
        self.config["tests_str"] += "only tutorial_get\n"
        params = {"nets": "net1 net2"}
        graph = TestGraph.parse_object_trees(
            restriction=self.config["tests_str"],
            object_restrs=self.config["vm_strs"],
            params=params,
        )

        worker1 = graph.workers["net1"]
        worker2 = graph.workers["net2"]

        # should clean a test node that is not reversible
        test_node1 = graph.get_nodes(param_val="explicit_clicked.+net1", unique=True)
        test_node2 = graph.get_nodes(param_val="explicit_clicked.+net2", unique=True)
        self.assertTrue(test_node1.default_clean_decision(worker1))
        self.assertTrue(test_node2.default_clean_decision(worker2))
        # should never clean an internal test node meant for other worker
        with self.assertRaises(RuntimeError):
            test_node1.default_clean_decision(worker2)
        with self.assertRaises(RuntimeError):
            test_node2.default_clean_decision(worker1)

        # should only clean a reversible leaf node if it globally finished
        test_node1 = graph.get_nodes(param_val="explicit_noop.+net1", unique=True)
        test_node2 = graph.get_nodes(param_val="explicit_noop.+net2", unique=True)
        swarm = TestSwarm("localhost", [worker1, worker2])
        TestSwarm.run_swarms = {swarm.id: swarm}
        node1_setup = list(test_node1.setup_nodes.keys())
        test_node1._picked_by_setup_nodes.register(node1_setup[0], worker1)
        node2_setup = list(test_node2.setup_nodes.keys())
        test_node2._picked_by_setup_nodes.register(node2_setup[0], worker2)
        # should never clean an internal test node meant for other worker despite the above
        with self.assertRaises(RuntimeError):
            test_node1.default_clean_decision(worker2)
        with self.assertRaises(RuntimeError):
            test_node2.default_clean_decision(worker1)
        self.assertFalse(test_node1.default_clean_decision(worker1))
        self.assertFalse(test_node2.default_clean_decision(worker2))
        test_node1.finished_worker = worker1
        self.assertFalse(test_node1.default_clean_decision(worker1))
        self.assertFalse(test_node2.default_clean_decision(worker2))
        test_node2.finished_worker = worker2
        self.assertTrue(test_node1.default_clean_decision(worker1))
        self.assertTrue(test_node2.default_clean_decision(worker2))

        # should not clean a reversible test node with still rerunning workers
        test_node1.results += [{"name": "explicit_noop.+net1", "status": "UNKNOWN"}]
        self.assertFalse(test_node1.default_clean_decision(worker1))
        self.assertFalse(test_node2.default_clean_decision(worker2))

        # should only clean a reversible setup node if it is globally cleanup ready
        test_node1 = graph.get_nodes(param_val="client_noop.+net1", unique=True)
        test_node2 = graph.get_nodes(param_val="client_noop.+net2", unique=True)
        test_node1.finished_worker = worker1
        test_node2.finished_worker = worker2
        node1_setup = list(test_node1.setup_nodes.keys())
        test_node1._picked_by_setup_nodes.register(node1_setup[0], worker1)
        node2_setup = list(test_node2.setup_nodes.keys())
        test_node2._picked_by_setup_nodes.register(node2_setup[0], worker2)
        node1_cleanup = list(test_node1.cleanup_nodes.keys())
        self.assertGreater(len(node1_cleanup), 0)
        for node in node1_cleanup:
            test_node1.drop_child(node, worker1)
        self.assertFalse(test_node1.default_clean_decision(worker1))
        self.assertFalse(test_node2.default_clean_decision(worker2))
        node2_cleanup = list(test_node2.cleanup_nodes.keys())
        self.assertGreater(len(node2_cleanup), 0)
        for node in node2_cleanup:
            test_node2.drop_child(node, worker2)
        self.assertTrue(test_node1.default_clean_decision(worker1))
        self.assertTrue(test_node2.default_clean_decision(worker2))

    def test_prefix_priority(self):
        """Test the default priority policy for test node prefixes."""
        self.assertEqual(TestNode.prefix_priority("3-net1vm1", "3-net1vm1"), 0)
        # simple comparison for leaf nodes
        self.assertEqual(TestNode.prefix_priority("3-net1vm1", "5-net1vm1"), -2)
        self.assertEqual(TestNode.prefix_priority("6-net1vm1", "3-net1vm1"), 3)
        # prioritize leaf node from derivative node
        self.assertEqual(TestNode.prefix_priority("3-net1vm1vm2", "3a1-net1vm1vm2"), -1)
        self.assertEqual(TestNode.prefix_priority("3-net1vm1vm2", "3b1-net1vm1vm2"), -1)
        self.assertEqual(TestNode.prefix_priority("3-net1vm1vm2", "3c1-net1vm1vm2"), -1)
        self.assertEqual(TestNode.prefix_priority("3-net1vm1vm2", "3d1-net1vm1vm2"), -1)
        # prioritize alpha category
        self.assertEqual(TestNode.prefix_priority("3b1-net1vm1vm2vm3", "3a1-net1vm1vm2vm3"), 1)
        self.assertEqual(TestNode.prefix_priority("3c1-net1vm1vm2vm3", "3b1-net1vm1vm2vm3"), 1)
        self.assertEqual(TestNode.prefix_priority("3d1-net1vm1vm2vm3", "3c1-net1vm1vm2vm3"), 1)
        # nested matching
        self.assertEqual(TestNode.prefix_priority("3b2-net1vm1vm2vm3", "3b1-net1vm1vm2vm3"), 1)
        self.assertEqual(TestNode.prefix_priority("3b2a1-net1vm1vm2vm3", "3b2-net1vm1vm2vm3"), 1)
        self.assertEqual(TestNode.prefix_priority("3b2c1-net1vm1vm2vm3", "3b2a1-net1vm1vm2vm3"), 1)
        # error handling for unterminated equal prefixes
        with self.assertRaises(ValueError):
            TestNode.prefix_priority("5d2", "5d2-net1vm2")
        with self.assertRaises(ValueError):
            TestNode.prefix_priority("5d2-net1vm2", "5d2")

    def test_pick_priority_prefix(self):
        """Test that pick priority prioritizes workers and then secondary criteria."""
        flat_net = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        flat_net.update_restrs(self.config["vm_strs"])
        worker = TestWorker(flat_net)
        full_components = TestGraph.parse_components_for_object(flat_net, "nets", "", unflatten=True)
        full_net = full_components[-1]

        node = TestGraph.parse_node_from_object(full_net, "normal..tutorial1")
        node1 = TestGraph.parse_node_from_object(full_net, "normal..tutorial1", prefix="1")
        node2 = TestGraph.parse_node_from_object(full_net, "normal..tutorial2", prefix="2")
        node.descend_from_node(node1, flat_net)
        node.descend_from_node(node2, flat_net)
        node1.descend_from_node(node, flat_net)
        node2.descend_from_node(node, flat_net)
        worker = TestWorker(flat_net)

        # prefix based lesser node1 since node1 < node2 at prefix
        picked_child = node.pick_child(worker)
        self.assertEqual(picked_child, node1)
        picked_parent = node.pick_parent(worker)
        self.assertEqual(picked_parent, node1)

        # lesser node2 has 1 worker less now
        self.assertEqual(node1._picked_by_cleanup_nodes.get_counters(), 1)
        picked_parent = node.pick_parent(worker)
        self.assertEqual(picked_parent, node2)
        self.assertEqual(node1._picked_by_setup_nodes.get_counters(), 1)
        picked_child = node.pick_child(worker)
        self.assertEqual(picked_child, node2)

        # resort to prefix again now that both nodes have been picked
        picked_child = node.pick_child(worker)
        self.assertEqual(picked_child, node1)
        picked_parent = node.pick_parent(worker)
        self.assertEqual(picked_parent, node1)

    def test_pick_priority_bridged(self):
        """Test that pick priority prioritizes workers and then secondary criteria."""
        flat_net = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        flat_net.update_restrs(self.config["vm_strs"])
        worker = TestWorker(flat_net)
        full_components = TestGraph.parse_components_for_object(flat_net, "nets", "", unflatten=True)
        full_net = full_components[-1]

        node = TestGraph.parse_node_from_object(full_net, "normal..tutorial1")
        node1 = TestGraph.parse_node_from_object(full_net, "normal..tutorial1", prefix="1")
        node2 = TestGraph.parse_node_from_object(full_net, "normal..tutorial1", prefix="2")
        node3 = TestGraph.parse_node_from_object(full_net, "normal..tutorial2", prefix="3")
        node.descend_from_node(node1, flat_net)
        node.descend_from_node(node2, flat_net)
        node.descend_from_node(node3, flat_net)
        node1.descend_from_node(node, flat_net)
        node2.descend_from_node(node, flat_net)
        node3.descend_from_node(node, flat_net)
        worker = TestWorker(flat_net)
        node1.bridge_with_node(node2)

        # lesser node1 by prefix to begin with
        picked_child = node.pick_child(worker)
        self.assertEqual(picked_child, node1)
        picked_parent = node.pick_parent(worker)
        self.assertEqual(picked_parent, node1)

        # lesser node3 has fewer picked nodes in comparison to the bridged node1 and node2
        picked_child = node.pick_child(worker)
        self.assertEqual(picked_child, node3)
        picked_parent = node.pick_parent(worker)
        self.assertEqual(picked_parent, node3)

    def test_pick_and_drop_node(self):
        """Test that parents and children are picked according to previous visits and cached."""
        flat_net = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        flat_net.update_restrs(self.config["vm_strs"])
        worker = TestWorker(flat_net)
        full_components = TestGraph.parse_components_for_object(flat_net, "nets", "", unflatten=True)
        full_net = full_components[-1]

        node = TestGraph.parse_node_from_object(full_net, "normal..tutorial1")
        child_node1 = TestGraph.parse_node_from_object(full_net, "normal..tutorial1", prefix="1")
        child_node2 = TestGraph.parse_node_from_object(full_net, "normal..tutorial2", prefix="2")
        child_node1.descend_from_node(node, flat_net)
        child_node2.descend_from_node(node, flat_net)
        worker = TestWorker(flat_net)

        picked_child = node.pick_child(worker)
        self.assertEqual(picked_child, child_node1)
        self.assertIn(worker.id, picked_child._picked_by_setup_nodes.get_workers(node))
        node.drop_child(picked_child, worker)
        self.assertIn(worker.id, node._dropped_cleanup_nodes.get_workers(picked_child))
        picked_child = node.pick_child(worker)
        self.assertEqual(picked_child, child_node2)
        self.assertIn(worker.id, picked_child._picked_by_setup_nodes.get_workers(node))
        node.drop_child(picked_child, worker)
        self.assertIn(worker.id, node._dropped_cleanup_nodes.get_workers(picked_child))

        picked_parent = picked_child.pick_parent(worker)
        self.assertEqual(picked_parent, node)
        self.assertIn(worker.id, picked_parent._picked_by_cleanup_nodes.get_workers(picked_child))
        picked_child.drop_parent(picked_parent, worker)
        self.assertIn(worker.id, picked_parent._dropped_cleanup_nodes.get_workers(picked_child))

    def test_pick_and_drop_bridged(self):
        """Test for correctly shared picked and dropped nodes across bridged nodes."""
        flat_net1 = TestGraph.parse_flat_objects("net1", "nets", params={"only_vm1": "CentOS"}, unique=True)
        worker1 = TestWorker(flat_net1)
        flat_net2 = TestGraph.parse_flat_objects("net2", "nets", params={"only_vm1": "CentOS"}, unique=True)
        worker2 = TestWorker(flat_net2)

        graph = TestGraph()
        node1 = graph.parse_composite_nodes("normal..tutorial1", flat_net1, unique=True)
        node2 = graph.parse_composite_nodes("normal..tutorial1", flat_net2, unique=True)
        node13 = graph.parse_composite_nodes("normal..tutorial2", flat_net1, unique=True)
        node23 = graph.parse_composite_nodes("normal..tutorial2", flat_net2, unique=True)

        # not picking or dropping any parent results in empty but equal registers
        node1.descend_from_node(node13, flat_net1)
        node2.descend_from_node(node23, flat_net2)
        node1.bridge_with_node(node2)
        node13.bridge_with_node(node23)
        self.assertEqual(node23._picked_by_cleanup_nodes, node13._picked_by_cleanup_nodes)
        self.assertEqual(node2._dropped_setup_nodes, node1._dropped_setup_nodes)

        # picking parent of node1 and dropping parent of node2 has shared effect
        self.assertEqual(node1.pick_parent(worker1), node13)
        self.assertEqual(node13._picked_by_cleanup_nodes.get_workers(node1), {worker1.id})
        self.assertEqual(node23._picked_by_cleanup_nodes.get_workers(node2), {worker1.id})
        node2.drop_parent(node23, worker2)
        self.assertEqual(node1._dropped_setup_nodes.get_workers(node13), {worker2.id})
        self.assertEqual(node2._dropped_setup_nodes.get_workers(node23), {worker2.id})

    def test_pull_locations(self):
        """Test that all setup get locations for a node are properly updated."""
        flat_net = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        flat_net.update_restrs(self.config["vm_strs"])
        worker = TestWorker(flat_net)
        full_components = TestGraph.parse_components_for_object(flat_net, "nets", "", unflatten=True)
        full_net = full_components[-1]

        node = TestGraph.parse_node_from_object(full_net, "normal..tutorial1", params=self.config["param_dict"])
        parent_node = TestGraph.parse_node_from_object(full_net, "normal..tutorial1", params=self.config["param_dict"])
        worker = TestWorker(flat_net)
        swarm = TestSwarm("localhost", [worker])
        TestSwarm.run_swarms = {swarm.id: swarm}
        # nets host is a runtime parameter
        worker.params["nets_host"] = "some_host"
        # could also be result from a previous job, not determined here
        parent_node.results = [{"name": "tutorial1.net1",
                                "status": "PASS", "time_elapsed": 3}]
        # parent nodes was parsed as dependency of node via its vm1 object
        node.descend_from_node(parent_node, mock.MagicMock(long_suffix="vm1"))

        node.pull_locations()
        get_locations = node.params.objects("get_location_vm1")
        self.assertEqual(len(get_locations), 2)
        self.assertEqual(get_locations[0], ":" + node.params["shared_pool"])
        self.assertEqual(get_locations[1], worker.id + ":" + node.params["swarm_pool"])
        # parameters to access the worker location should also be provided for the test
        self.assertEqual(node.params[f"nets_host_{worker.id}"], worker.params[f"nets_host"])

        # an impossible situation with different worker ids must be validated against
        with mock.patch('virttest.cartgraph.TestNode.shared_result_worker_ids', new_callable=mock.PropertyMock) as mock_ids:
            mock_ids.return_value = {"net2"}
            with self.assertRaises(RuntimeError):
                node.pull_locations()

    def test_pull_locations_bridged(self):
        """Test that all setup get locations for a node are properly updated."""
        flat_net1 = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        flat_net2 = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        worker = TestWorker(flat_net1)

        flat_net1.update_restrs(self.config["vm_strs"])
        full_components = TestGraph.parse_components_for_object(flat_net1, "nets", "", unflatten=True)
        full_net1 = full_components[-1]
        flat_net2.update_restrs(self.config["vm_strs"])
        full_components = TestGraph.parse_components_for_object(flat_net2, "nets", "", unflatten=True)
        full_net2 = full_components[-1]

        node1 = TestGraph.parse_node_from_object(full_net1, "normal..tutorial1", params=self.config["param_dict"])
        node2 = TestGraph.parse_node_from_object(full_net2, "normal..tutorial1", params=self.config["param_dict"])
        parent_node1 = TestGraph.parse_node_from_object(full_net1, "normal..tutorial1", params=self.config["param_dict"])
        parent_node2 = TestGraph.parse_node_from_object(full_net2, "normal..tutorial1", params=self.config["param_dict"])
        worker1 = TestWorker(flat_net1)
        worker2 = TestWorker(flat_net2)
        swarm = TestSwarm("localhost", [worker1, worker2])
        TestSwarm.run_swarms = {swarm.id: swarm}
        # nets host is a runtime parameter
        worker1.params["nets_host"] = "some_host"
        worker2.params["nets_host"] = "other_host"
        # could also be result from a previous job, not determined here
        parent_node1.results = [{"name": "tutorial1.net1",
                                 "status": "PASS", "time_elapsed": 3}]
        # parent nodes was parsed as dependency of node via its vm1 object
        node1.descend_from_node(parent_node1, mock.MagicMock(long_suffix="vm1"))
        node2.descend_from_node(parent_node2, mock.MagicMock(long_suffix="vm1"))
        node1.bridge_with_node(node2)
        parent_node1.bridge_with_node(parent_node2)

        node1.pull_locations()
        get_locations = node1.params.objects("get_location_vm1")
        self.assertEqual(len(get_locations), 2)
        self.assertEqual(get_locations[0], ":" + node1.params["shared_pool"])
        self.assertEqual(get_locations[1], worker1.id + ":" + node1.params["swarm_pool"])
        # parameters to access the worker location should also be provided for the test
        self.assertEqual(node1.params[f"nets_host_{worker1.id}"], worker1.params[f"nets_host"])

        node2.pull_locations()
        get_locations = node2.params.objects("get_location_vm1")
        self.assertEqual(len(get_locations), 2)
        self.assertEqual(get_locations[0], ":" + node1.params["shared_pool"])
        self.assertEqual(get_locations[1], worker1.id + ":" + node1.params["swarm_pool"])
        # parameters to access the worker location should also be provided for the test
        self.assertEqual(node2.params[f"nets_host_{worker1.id}"], worker1.params[f"nets_host"])

    def test_validation(self):
        """Test graph (and component) retrieval and validation methods."""
        flat_net = TestGraph.parse_flat_objects("net1", "nets", params={"only_vm1": "CentOS"}, unique=True)
        graph = TestGraph()
        test_node = graph.parse_composite_nodes("normal..tutorial1", flat_net, unique=True)

        self.assertEqual(len([o for o in test_node.objects if o.suffix == "vm1"]), 1)
        test_object = [o for o in test_node.objects if o.suffix == "vm1"][0]
        self.assertIn(test_object, test_node.objects)
        test_node.validate()
        test_node.objects.remove(test_object)
        with self.assertRaisesRegex(ValueError, r"^Additional parametric objects .+ not in .+$"):
            test_node.validate()
        test_node.objects.append(test_object)
        test_node.validate()
        test_node.params["vms"] = ""
        with self.assertRaisesRegex(ValueError, r"^Missing parametric objects .+ from .+$"):
            test_node.validate()

        # detect reflexive dependencies in the graph
        test_node = graph.parse_composite_nodes("normal..tutorial1", flat_net, unique=True)
        test_node.descend_from_node(test_node, flat_net)
        with self.assertRaisesRegex(ValueError, r"^Detected reflexive dependency of"):
            test_node.validate()


@mock.patch('virttest.cartgraph.worker.remote.wait_for_login', mock.MagicMock())
@mock.patch('virttest.cartgraph.node.door', DummyStateControl)
@mock.patch('avocado_vt.plugins.runner.SpawnerDispatcher', mock.MagicMock())
@mock.patch.object(TestRunner, 'run_test_task', DummyTestRun.mock_run_test_task)
class CartesianGraphTest(Test):

    def setUp(self):
        self.config = {}
        self.config["param_dict"] = {"nets": "net1", "test_timeout": 100,
                                     # test additional optional syncing for non-default cases
                                     "pool_filter": "copy",
                                     "shared_pool": "/mnt/local/images/shared"}
        self.config["tests_str"] = "only normal\n"
        self.config["vm_strs"] = {"vm1": "only CentOS\n", "vm2": "only Win10\n", "vm3": "only Ubuntu\n"}

        self.prefix = ""

        self.loader = TestLoader(config=self.config, extra_params={})
        self.job = mock.MagicMock()
        self.job.logdir = "."
        self.job.timeout = 6000
        self.job.result = mock.MagicMock()
        self.job.result.tests = []
        self.job.config = self.config
        self.runner = TestRunner()
        self.runner.job = self.job
        self.runner.status_server = self.job

        DummyTestRun.asserted_tests = []
        self.shared_pool = ":" + self.config["param_dict"]["shared_pool"]
        DummyStateControl.asserted_states = {"check": {}, "get": {}, "set": {}, "unset": {}}
        DummyStateControl.asserted_states["check"] = {"install": {self.shared_pool: False},
                                                      "customize": {self.shared_pool: False}, "on_customize": {self.shared_pool: False},
                                                      "connect": {self.shared_pool: False},
                                                      "linux_virtuser": {self.shared_pool: False}, "windows_virtuser": {self.shared_pool: False}}
        DummyStateControl.asserted_states["get"] = {"install": {self.shared_pool: 0},
                                                    "customize": {self.shared_pool: 0}, "on_customize": {self.shared_pool: 0},
                                                    "connect": {self.shared_pool: 0},
                                                    "linux_virtuser": {self.shared_pool: 0}, "windows_virtuser": {self.shared_pool: 0}}

    def _load_for_parsing(self, restriction, params):
        graph = TestGraph()
        graph.restrs.update(self.job.config["vm_strs"])
        loaded_nodes = TestGraph.parse_flat_nodes(restriction)
        for node in loaded_nodes:
            node.update_restrs(self.job.config["vm_strs"])
        graph.new_nodes(loaded_nodes)
        graph.parse_shared_root_from_object_roots()
        graph.new_workers(TestGraph.parse_workers(params))
        return graph

    def _run_traversal(self, graph, params=None):
        params = params or {"test_timeout": 100}
        slot_workers = sorted(list(graph.workers.values()), key=lambda x: x.params["name"])
        graph.runner = self.runner
        loop = self.runner.loop
        to_traverse = [graph.traverse_object_trees(s, params) for s in slot_workers]
        loop.run_until_complete(asyncio.wait_for(asyncio.gather(*to_traverse), None))
        self.assertEqual(len(DummyTestRun.asserted_tests), 0, "Some tests weren't run: %s" % DummyTestRun.asserted_tests)

    def test_flag_children_all(self):
        """Test for correct node children flagging of a complete Cartesian graph."""
        self.config["param_dict"]["nets"] = "net1"
        self.config["param_dict"]["vms"] = "vm1"
        self.config["tests_str"] = "only nonleaves\n"
        self.config["tests_str"] += "only connect\n"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )

        graph.flag_children(flag_type="run", flag=lambda self, slot: False)
        DummyTestRun.asserted_tests = [
        ]
        self._run_traversal(graph, self.config["param_dict"])

        graph.flag_children(flag_type="run", flag=lambda self, slot: True)
        graph.flag_children(object_name="image1_vm1", flag_type="run", flag=lambda self, slot: False)
        DummyTestRun.asserted_tests = [
        ]
        self._run_traversal(graph, self.config["param_dict"])

    def test_flag_children(self):
        """Test for correct node children flagging for a given node."""
        self.config["param_dict"]["nets"] = "net1"
        self.config["param_dict"]["vms"] = "vm1"
        self.config["tests_str"] = "only nonleaves\n"
        self.config["tests_str"] += "only connect\n"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )

        graph.flag_children(flag_type="run", flag=lambda self, slot: False)
        graph.flag_children(node_name="customize", flag_type="run",
                            flag=lambda self, slot: not self.is_finished(slot))
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$"},
            {"shortname": "^nonleaves.internal.automated.connect.vm1", "vms": "^vm1$"},
        ]
        self._run_traversal(graph, self.config["param_dict"])

    def test_flag_children_worker(self):
        """Test for correct node children flagging for a given node."""
        self.config["param_dict"]["nets"] = "net1 net2"
        self.config["tests_str"] = "only nonleaves\n"
        self.config["tests_str"] += "only connect\n"
        self.config["param_dict"]["vms"] = "vm1"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )

        # disable running the entire multi-graph by default
        graph.flag_children(flag_type="run", flag=lambda self, slot: False)
        # net1 will run as in simpler cases
        graph.flag_children(node_name="customize", worker_name="net1", flag_type="run",
                            flag=lambda self, slot: not self.is_finished(slot))
        # net2 will run from connect to connect, thus running zero nodes
        graph.flag_children(node_name="connect", worker_name="net2", flag_type="run",
                            flag=lambda self, slot: not self.is_finished(slot))
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$"},
            {"shortname": "^nonleaves.internal.automated.connect.vm1", "vms": "^vm1$"},
        ]
        self._run_traversal(graph, self.config["param_dict"])

    def test_flag_intersection_all(self):
        """Test for correct node flagging of a Cartesian graph with itself."""
        self.config["param_dict"]["nets"] = "net1"
        self.config["param_dict"]["vms"] = "vm1"
        self.config["tests_str"] = "only nonleaves\n"
        self.config["tests_str"] += "only connect\n"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )
        graph.flag_intersection(graph, flag_type="run", flag=lambda self, slot: False)
        DummyTestRun.asserted_tests = [
        ]
        self._run_traversal(graph, self.config["param_dict"])

    def test_flag_intersection(self):
        """Test for correct node intersection of two Cartesian graphs."""
        self.config["param_dict"]["nets"] = "net1"
        self.config["param_dict"]["vms"] = "vm1"
        self.config["tests_str"] = "only nonleaves\n"
        tests_str1 = self.config["tests_str"] + "only connect\n"
        tests_str2 = self.config["tests_str"] + "only customize\n"
        graph = TestGraph.parse_object_trees(
            None, tests_str1,
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )
        reuse_graph = TestGraph.parse_object_trees(
            None, tests_str2,
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )

        #graph.flag_intersection(graph, flag_type="run", flag=lambda self, slot: slot not in self.workers)
        graph.flag_intersection(reuse_graph, flag_type="run", flag=lambda self, slot: False)
        DummyTestRun.asserted_tests = [
            {"shortname": "^nonleaves.internal.automated.connect.vm1", "vms": "^vm1$"},
        ]
        self._run_traversal(graph, self.config["param_dict"])

    def test_get_objects(self):
        """Test object retrieval with various arguments and thus calls."""
        graph = TestGraph()
        graph.new_objects([n for n in TestGraph.parse_suffix_objects("vms")])
        self.assertEqual(len(graph.objects), 6)
        get_objects = graph.get_objects(param_val=r"vm\d")
        self.assertEqual(len(get_objects), len(graph.objects))
        get_objects = graph.get_objects(param_val="vm1")
        self.assertEqual(len(get_objects), 2)
        get_objects = graph.get_objects(param_val=r"\.CentOS", subset=get_objects)
        self.assertEqual(len(get_objects), 1)
        get_objects = graph.get_objects("os_type", param_val="linux", subset=get_objects)
        self.assertEqual(len(get_objects), 1)
        get_objects = graph.get_objects(param_key="os_variant", param_val="centos", subset=get_objects)
        self.assertEqual(len(get_objects), 1)
        get_node = graph.get_nodes(param_key="os_type", param_val="linux",
                                      subset=get_objects, unique=True)
        self.assertIn(get_node, get_objects)
        get_nodes = graph.get_nodes(param_val="vm1", subset=[])
        self.assertEqual(len(get_nodes), 0)

    def test_get_nodes_by_name(self):
        """Test node retrieval by name using a trie as an index."""
        graph = TestGraph()
        graph.new_nodes(TestGraph.parse_flat_nodes("all..tutorial3"))
        self.assertEqual(len(graph.nodes), 17)
        get_nodes = graph.get_nodes_by_name("tutorial3")
        self.assertEqual(len(get_nodes), len(graph.nodes))
        get_nodes = graph.get_nodes_by_name("tutorial3.remote")
        self.assertEqual(len(get_nodes), 16)
        get_nodes = graph.get_nodes_by_name("object")
        self.assertEqual(len(get_nodes), 8)
        get_nodes = graph.get_nodes_by_name("object.control")
        self.assertEqual(len(get_nodes), 4)
        get_nodes = graph.get_nodes_by_name("tutorial3.remote.object.control.decorator")
        self.assertEqual(len(get_nodes), 2)

    def test_get_nodes(self):
        """Test node retrieval with various arguments and thus calls."""
        graph = TestGraph()
        graph.new_nodes(TestGraph.parse_flat_nodes("all..tutorial3"))
        self.assertEqual(len(graph.nodes), 17)
        get_nodes = graph.get_nodes(param_val="tutorial3")
        self.assertEqual(len(get_nodes), len(graph.nodes))
        get_nodes = graph.get_nodes(param_val="tutorial3.remote")
        self.assertEqual(len(get_nodes), 16)
        get_nodes = graph.get_nodes(param_val=r"\.object", subset=get_nodes)
        self.assertEqual(len(get_nodes), 8)
        get_nodes = graph.get_nodes("remote_control_check", param_val="yes", subset=get_nodes)
        self.assertEqual(len(get_nodes), 4)
        get_nodes = graph.get_nodes(param_key="remote_decorator_check", param_val="yes", subset=get_nodes)
        self.assertEqual(len(get_nodes), 2)
        get_node = graph.get_nodes(param_key="remote_util_check", param_val="yes",
                                      subset=get_nodes, unique=True)
        self.assertIn(get_node, get_nodes)
        get_nodes = graph.get_nodes(param_val="tutorial3", subset=[])
        self.assertEqual(len(get_nodes), 0)

    def test_object_node_incompatible(self):
        """Test incompatibility of parsed tests and pre-parsed available objects."""
        self.config["tests_str"] += "only tutorial1\n"
        self.config["vm_strs"] = {"vm2": "only Win10\n", "vm3": "only Ubuntu\n"}
        with self.assertRaises(param.EmptyCartesianProduct):
            TestGraph.parse_object_nodes(None, self.config["tests_str"], prefix=self.prefix,
                                         object_restrs=self.config["vm_strs"],
                                         params=self.config["param_dict"])

    def test_object_node_intersection(self):
        """Test restricted vms-tests nonempty intersection of parsed tests and pre-parsed available objects."""
        self.config["tests_str"] += "only tutorial1,tutorial_get\n"
        self.config["vm_strs"] = {"vm1": "only CentOS\n", "vm2": "only Win10\n"}
        nodes, objects = TestGraph.parse_object_nodes(None, self.config["tests_str"], prefix=self.prefix,
                                                      object_restrs=self.config["vm_strs"],
                                                      params=self.config["param_dict"])
        object_suffixes = [o.suffix for o in objects]
        self.assertIn("vm1", object_suffixes)
        # due to lacking vm3 tutorial_get will not be parsed and the only already parsed vm remains vm1
        self.assertNotIn("vm2", object_suffixes)
        # vm3 is fully lacking
        self.assertNotIn("vm3", object_suffixes)
        for n in nodes:
            if "tutorial1" in n.params["name"]:
                break
        else:
            raise AssertionError("The tutorial1 variant must be present in the object-node intersection")
        for n in nodes:
            if "tutorial_get" in n.params["name"]:
                raise AssertionError("The tutorial_get variant must be skipped since vm3 is not available")

    def test_parse_cloned_branches_for_node_and_object(self):
        """Test default parsing and retrieval of cloned branches for a set of parent test nodes."""
        graph = TestGraph()
        flat_object = TestGraph.parse_flat_objects("net1", "nets",
                                                   params={"only_vm1": "CentOS", "only_vm2": "Win10", "only_vm3": "Ubuntu"},
                                                   unique=True)
        full_parents = graph.parse_composite_nodes("normal..tutorial_gui", flat_object)
        self.assertEqual(len(full_parents), 2)
        full_node = graph.parse_composite_nodes("leaves..tutorial_get..implicit_both", flat_object, unique=True)
        # the clone source setup has to be fully defined to clone it as setup for the clones
        full_node.descend_from_node(full_parents[0], flat_object)

        clones = graph.parse_cloned_branches_for_node_and_object(full_node, flat_object, full_parents)
        self.assertEqual(len(clones), 2)
        self.assertTrue(full_node.prefix.startswith("0"))
        self.assertEqual(full_node.cloned_nodes, tuple(clones))
        for child, parent in zip(clones, full_parents):
            if child != clones[0]:
                self.assertIn("d", child.prefix)
            self.assertNotEqual(full_node.recipe, child.recipe)
            # the parametrization of clones is still already covered at the next scope
            self.assertIn(parent, child.setup_nodes)
            self.assertIn(child, parent.cleanup_nodes)
            self.assertEqual(child.bridged_nodes, full_node.bridged_nodes)

        # deeper cloning must also restore bridging among grandchildren
        grandchildren = graph.parse_composite_nodes("leaves..tutorial_finale", flat_object)
        self.assertEqual(len(grandchildren), 1)
        grandchild = grandchildren[0]
        grandchild.descend_from_node(full_node, flat_object)
        clones = graph.parse_cloned_branches_for_node_and_object(full_node, flat_object, full_parents)
        self.assertEqual(len(clones), 2)
        self.assertTrue(grandchild.prefix.startswith("0"))
        self.assertEqual(len(grandchild.cloned_nodes), 2)
        for child, parent in zip(grandchild.cloned_nodes, clones):
            if child != grandchild.cloned_nodes[0]:
                self.assertIn("d", child.prefix)
            self.assertNotEqual(grandchild.recipe, child.recipe)
            self.assertEqual(len(set(child.setup_nodes) - set(clones)), 0)
            self.assertEqual(len(set(parent.cleanup_nodes) - set(grandchild.cloned_nodes)), 0)
            self.assertEqual(child.bridged_nodes, grandchild.bridged_nodes)

    def test_parse_branches_for_node_and_object(self):
        """Test default parsing and retrieval of branches for a pair of test node and object."""
        graph = TestGraph()
        flat_node = TestGraph.parse_flat_nodes("normal..tutorial1", unique=True)
        flat_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)

        parents, children = graph.parse_branches_for_node_and_object(flat_node, flat_object)
        self.assertEqual(len(parents), 2)
        self.assertEqual([n.prefix for n in parents], ["1a1", "1b1a1"])
        # validate cache is exactly as expected, namely just the newly parsed nodes
        self.assertEqual(len(graph.nodes), len(parents + children))
        self.assertEqual(set(graph.nodes), set(parents + children))

        self.assertEqual(len(graph.objects), 6)
        full_nets = sorted([o for o in graph.objects if o.key == "nets"], key=lambda x: x.params["name"])
        self.assertEqual(len(full_nets), 2)
        full_vms = sorted([o for o in graph.objects if o.key == "vms"], key=lambda x: x.params["name"])
        self.assertEqual(len(full_vms), 2)
        full_images = [o for o in graph.objects if o.key == "images"]
        self.assertEqual(len(full_images), 2)

        self.assertEqual(len(children), 2)
        self.assertEqual([n.prefix for n in children], ["1", "1b1"])
        for i in range(len(children)):
            self.assertEqual(children[i].objects[0], full_nets[i])
            self.assertEqual(children[i].objects[0].components[0], full_vms[i])

        # any parents and children are now reused
        reused_parent, reused_child = parents[0], children[0]
        reparsed_parent, reparsed_child = parents[1], children[1]
        parents, children = graph.parse_branches_for_node_and_object(flat_node, flat_object)
        self.assertEqual(len(parents), 0)
        self.assertEqual(len(children), 0)
        graph._nodes = []
        graph.nodes_index = PrefixTree()
        graph.new_nodes([reused_parent, reused_child])
        parents, children = graph.parse_branches_for_node_and_object(flat_node, flat_object)
        self.assertEqual(len(parents), 1)
        self.assertEqual(len(children), 1)
        self.assertEqual(parents[0].params["name"], reparsed_parent.params["name"])
        self.assertEqual(children[0].params["name"], reparsed_child.params["name"])

        # make sure the node reuse does not depend on test set restrictions
        flat_node = TestGraph.parse_flat_nodes("all..tutorial1", unique=True)
        parents, children = graph.parse_branches_for_node_and_object(flat_node, flat_object)
        self.assertEqual(len(parents), 0)
        self.assertEqual(len(children), 0)

    def test_parse_branches_for_node_and_object_with_bridging(self):
        """Test that parsing and retrieval of branches also bridges worker-related nodes."""
        flat_object1 = TestGraph.parse_flat_objects("net1", "nets",
                                                    params={"only_vm1": "CentOS", "only_vm2": "Win10", "only_vm3": "Ubuntu"},
                                                    unique=True)
        flat_object2 = TestGraph.parse_flat_objects("net2", "nets",
                                                    params={"only_vm1": "CentOS", "only_vm2": "Win10", "only_vm3": "Ubuntu"},
                                                    unique=True)

        graph = TestGraph()

        graph.new_nodes(graph.parse_composite_nodes("normal..tutorial1", flat_object1))
        full_node1 = graph.get_nodes(param_val="tutorial1.+net1", unique=True)
        _, children = graph.parse_branches_for_node_and_object(full_node1, flat_object1)
        self.assertEqual(len(children), 1)
        self.assertIn(full_node1, children)
        self.assertEqual(len(full_node1.bridged_nodes), 0)

        graph.new_nodes(graph.parse_composite_nodes("normal..tutorial1", flat_object2))
        full_node2 = graph.get_nodes(param_val="tutorial1.+net2", unique=True)
        _, children = graph.parse_branches_for_node_and_object(full_node2, flat_object2)
        self.assertEqual(len(children), 1)
        self.assertIn(full_node2, children)
        self.assertEqual(len(full_node2.bridged_nodes), 1)
        self.assertEqual(len(full_node1.bridged_nodes), 1)
        self.assertIn(full_node1, full_node2.bridged_nodes)
        self.assertIn(full_node2, full_node1.bridged_nodes)

    def test_parse_branches_for_node_and_object_with_cloning(self):
        """Test default parsing and retrieval of branches for a pair of cloned test node and object."""
        flat_object = TestGraph.parse_flat_objects("net1", "nets",
                                                   params={"only_vm1": "CentOS", "only_vm2": "Win10", "only_vm3": "Ubuntu"},
                                                   unique=True)
        flat_node = TestGraph.parse_flat_nodes("leaves..tutorial_get..implicit_both", unique=True)

        graph = TestGraph()

        parents, children = graph.parse_branches_for_node_and_object(flat_node, flat_object)
        self.assertEqual(len([p for p in parents if "tutorial_gui" in p.id]), 2)
        # parents via two separate test objects followed by a second parent
        self.assertEqual([n.prefix for n in parents], ["1a1", "1a1", "1a2"])
        # validate cache is exactly as expected, namely just the newly parsed nodes
        self.assertEqual(len(graph.nodes), len(parents + children))
        self.assertEqual(set(graph.nodes), set(parents + children))

        self.assertEqual(len(graph.objects), 3+6+6)
        # nets are one triple, one double, and one single (triple for current, double and single for parents)
        full_nets = sorted([o for o in graph.objects if o.key == "nets"], key=lambda x: x.params["name"])
        self.assertEqual(len(full_nets), 3)
        # we always parse all vms independently of restrictions since they play the role of base for filtering
        full_vms = sorted([o for o in graph.objects if o.key == "vms"], key=lambda x: x.params["name"])
        self.assertEqual(len(full_vms), 6)
        full_images = [o for o in graph.objects if o.key == "images"]
        self.assertEqual(len(full_images), 6)

        self.assertEqual(len(children), 3)
        # extra duplicated clone
        self.assertEqual([n.prefix for n in children], ["01", "1", "1d1"])
        for i in range(len(children)):
            self.assertIn(children[i].objects[0], full_nets)
            self.assertTrue(set(children[i].objects[0].components) <= set(full_vms))

        parents, children = graph.parse_branches_for_node_and_object(flat_node, flat_object)
        self.assertEqual(len(parents), 0)

    def test_parse_branches_for_node_and_object_with_cloning_multivariant(self):
        """Test default parsing and retrieval of branches for a pair of cloned test node and object."""
        graph = TestGraph()
        # the test node restricts vm1 to CentOS in the config and it is not something that can be
        # overwritten as the user choices could only restrict further already restricted variants
        flat_node = TestGraph.parse_flat_nodes("leaves..tutorial_get..implicit_both",
                                               params={"only_vm2": "", "only_vm3": ""},
                                               unique=True)
        flat_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)

        # use params to overwrite the full node parameters and remove its default restriction on vm1
        parents, children = graph.parse_branches_for_node_and_object(flat_node, flat_object)
        # one variant of connect for the one variant of vm1 as needed restriction by implicit_both (default)
        self.assertEqual(len([p for p in parents if "connect" in p.id]), 1)
        # 4 variants of tutorial_gui for the 2x2 variants of vm1 and vm2 (as setup for vm2, user specified)
        self.assertEqual(len([p for p in parents if "tutorial_gui" in p.id]), 4)
        # parents via two separate test objects followed by a second parent then by reused vm2 byproduct parents
        self.assertEqual([n.prefix for n in parents], ["1a1", "1a1", "1a2", "1b2a1", "1b2a2"])
        # validate cache is exactly as expected, namely just the newly parsed nodes
        self.assertEqual(len(graph.nodes), len(parents + children))
        self.assertEqual(set(graph.nodes), set(parents + children))

        self.assertEqual(len(graph.objects), 7+6+6)
        # nets are one triple, one double, and one single (triple for current, double and single for parents)
        full_nets = sorted([o for o in graph.objects if o.key == "nets"], key=lambda x: x.params["name"])
        # all triple, two double (both of CentOS with each windows variant due to one-edge reusability), and one single (CentOS vm1)
        self.assertEqual(len(full_nets), 2**2+2+1)
        # we always parse all vms independently of restrictions since they play the role of base for filtering
        full_vms = sorted([o for o in graph.objects if o.key == "vms"], key=lambda x: x.params["name"])
        self.assertEqual(len(full_vms), 6)
        full_images = [o for o in graph.objects if o.key == "images"]
        self.assertEqual(len(full_images), 6)

        # the two Fedora children are excluded
        self.assertEqual(len(children), 3*2**(3-1))
        self.assertEqual(len([c for c in children if "implicit_both" in c.id]), 3*2**(3-1))
        self.assertEqual(len([c for c in children if "implicit_both" in c.id and "guisetup.noop" in c.id]), 2**(3-1))
        self.assertEqual(len([c for c in children if "implicit_both" in c.id and "guisetup.clicked" in c.id]), 2**(3-1))
        # four byproducts followed by four duplications
        self.assertEqual([n.prefix for n in children], ["01", "01b1", "01b2", "01b3",
                                                        "1", "1d1", "1b1", "1b1d1", "1b2", "1b2d1", "1b3", "1b3d1"])
        for i in range(len(children)):
            self.assertIn(children[i].objects[0], full_nets)
            self.assertTrue(set(children[i].objects[0].components) <= set(full_vms))

        parents, children = graph.parse_branches_for_node_and_object(flat_node, flat_object)
        self.assertEqual(len(parents), 0)
        for flat_node in TestGraph.parse_flat_nodes("leaves..tutorial_get"):
            parents, children = graph.parse_branches_for_node_and_object(flat_node, flat_object)
            self.assertEqual(len(parents), 0)

    def test_parse_branches_for_node_and_object_with_cloning_bridging(self):
        """Test parsing and retrieval of branches for bridged cloned test node and object."""
        flat_object1 = TestGraph.parse_flat_objects("net1", "nets",
                                                    params={"only_vm1": "CentOS", "only_vm2": "Win10", "only_vm3": "Ubuntu"},
                                                    unique=True)
        flat_object2 = TestGraph.parse_flat_objects("net2", "nets",
                                                    params={"only_vm1": "CentOS", "only_vm2": "Win10", "only_vm3": "Ubuntu"},
                                                    unique=True)
        flat_node = TestGraph.parse_flat_nodes("leaves..tutorial_get..implicit_both", unique=True)

        graph = TestGraph()

        parents1, children1 = graph.parse_branches_for_node_and_object(flat_node, flat_object1)
        self.assertEqual(len([p for p in parents1 if "tutorial_gui" in p.id]), 2)
        self.assertEqual(len(children1), 3)
        parents2, children2 = graph.parse_branches_for_node_and_object(flat_node, flat_object2)
        self.assertEqual(len([p for p in parents2 if "tutorial_gui" in p.id]), 2)
        self.assertEqual(len(children2), 3)
        for child1, child2 in zip(children1, children2):
            graph.parse_branches_for_node_and_object(child1, flat_object1)
            self.assertEqual(len(child1.bridged_nodes), 1)
            self.assertEqual(child1.bridged_nodes[0], child2)
            self.assertEqual(len(child2.bridged_nodes), 1)
            self.assertEqual(child2.bridged_nodes[0], child1)

        graph = TestGraph()

        # deeper cloning must also restore bridging among grandchildren
        composite_nodes = graph.parse_composite_nodes("leaves..tutorial_get..implicit_both", flat_object1)
        composite_nodes += graph.parse_composite_nodes("leaves..tutorial_get..implicit_both", flat_object2)
        self.assertEqual(len(composite_nodes), 2)
        graph.new_nodes(composite_nodes)
        grandchildren = graph.parse_composite_nodes("leaves..tutorial_finale", flat_object1)
        grandchildren += graph.parse_composite_nodes("leaves..tutorial_finale", flat_object2)
        graph.new_nodes(grandchildren)
        self.assertEqual(len(grandchildren), 2)
        for i in (0, 1):
            grandchildren[i].descend_from_node(composite_nodes[i], flat_object1 if i == 0 else flat_object2)
        graph.parse_branches_for_node_and_object(composite_nodes[0], flat_object1)
        graph.parse_branches_for_node_and_object(composite_nodes[1], flat_object1)
        self.assertEqual(composite_nodes[0].bridged_nodes, (composite_nodes[1], ))
        self.assertEqual(composite_nodes[1].bridged_nodes, (composite_nodes[0], ))
        cloned_grandchildren = graph.get_nodes(param_val="tutorial_finale.getsetup")
        self.assertEqual(len(cloned_grandchildren), 4)
        self.assertEqual(grandchildren[0].cloned_nodes, (cloned_grandchildren[0], cloned_grandchildren[1]))
        self.assertEqual(grandchildren[1].cloned_nodes, (cloned_grandchildren[2], cloned_grandchildren[3]))
        self.assertEqual(cloned_grandchildren[0].bridged_nodes, (cloned_grandchildren[2], ))
        self.assertEqual(cloned_grandchildren[1].bridged_nodes, (cloned_grandchildren[3], ))
        # make sure grandchildren descend from children properly
        for grandchild in cloned_grandchildren:
            self.assertEqual(len(grandchild.setup_nodes), 1)
            child = list(grandchild.setup_nodes.keys())[0]
            variant = "noop" if "noop" in child.id else "clicked"
            self.assertRegex(child.params["name"], f".implicit_both.+{variant}")
            dependency_object = flat_object1 if cloned_grandchildren.index(grandchild) in (0, 1) else flat_object2
            self.assertEqual(grandchild.setup_nodes[child], {dependency_object})
        # grandchildren must be cached too
        self.assertEqual(len(set(cloned_grandchildren) - set(graph.nodes)), 0)

    def test_parse_paths_to_object_roots(self):
        """Test correct expectation of parsing graph dependency paths from a leaf to all their object roots."""
        graph = TestGraph()
        flat_object = TestGraph.parse_flat_objects("net1", "nets", unique=True)
        flat_node = TestGraph.parse_flat_nodes("normal..tutorial1", unique=True)

        generator = graph.parse_paths_to_object_roots(flat_node, flat_object)
        flat_parents, flat_children, flat_node2 = next(generator)
        self.assertEqual(flat_node, flat_node2)
        self.assertNotIn(flat_node, flat_children)
        self.assertEqual(len(flat_children), 2)
        for child in flat_children:
            self.assertFalse(child.is_flat())
        self.assertEqual(len(flat_parents), 2)
        for parent in flat_parents:
            self.assertFalse(parent.is_flat())
        leaf_parents1, leaf_children1, leaf_node1 = next(generator)
        self.assertIn(leaf_node1, flat_children)
        self.assertEqual(len(leaf_children1), 0)
        self.assertEqual(len(leaf_parents1), 0)
        leaf_parents2, leaf_children2, leaf_node2 = next(generator)
        self.assertIn(leaf_node2, flat_children)
        self.assertEqual(len(leaf_children2), 0)
        self.assertEqual(len(leaf_parents2), 0)

    def test_parse_paths_to_object_roots_with_cloning_shallow(self):
        """Test parsing of complete paths to object roots with shallow cloning."""
        graph = TestGraph()
        flat_object = TestGraph.parse_flat_objects("net1", "nets",
                                                   params={"only_vm1": "CentOS", "only_vm2": "Win10", "only_vm3": "Ubuntu"},
                                                   unique=True)
        flat_node = TestGraph.parse_flat_nodes("leaves..tutorial_get..implicit_both", unique=True)

        generator = graph.parse_paths_to_object_roots(flat_node, flat_object)
        flat_parents, flat_children, _ = next(generator)
        self.assertEqual(len(flat_children), 3)
        self.assertEqual(len([p for p in flat_parents if "tutorial_gui" in p.id]), 2)
        leaf_parents1, leaf_children1, leaf_node1 = next(generator)
        self.assertIn(leaf_node1, flat_children)
        self.assertEqual(len(leaf_children1), 0)
        self.assertEqual(len(leaf_parents1), 0)
        leaf_parents2, leaf_children2, leaf_node2 = next(generator)
        self.assertIn(leaf_node2, flat_children)
        self.assertEqual(len(leaf_children2), 0)
        self.assertEqual(len(leaf_parents2), 0)
        leaf_parents3, leaf_children3, leaf_node3 = next(generator)
        self.assertIn(leaf_node3, flat_children)
        self.assertEqual(len(leaf_children3), 0)
        self.assertEqual(len(leaf_parents3), 0)

        next_parents1, next_children1, parent_node1 = next(generator)
        self.assertIn(parent_node1, flat_parents)
        # no more duplication
        self.assertEqual(len(next_children1), 0)
        self.assertGreaterEqual(len(next_parents1), 0)

    def test_parse_paths_to_object_roots_with_cloning_deep(self):
        """Test parsing of complete paths to object roots with deep cloning."""
        graph = TestGraph()
        flat_object = TestGraph.parse_flat_objects("net1", "nets",
                                                   params={"only_vm1": "CentOS", "only_vm2": "Win10", "only_vm3": "Ubuntu"},
                                                   unique=True)
        flat_node = TestGraph.parse_flat_nodes("leaves..tutorial_finale", unique=True)

        generator = graph.parse_paths_to_object_roots(flat_node, flat_object)
        flat_parents, flat_children, _ = next(generator)
        self.assertEqual(len(flat_children), 1)
        self.assertEqual(len([p for p in flat_parents if "tutorial_get.implicit_both" in p.id]), 1)
        leaf_parents1, leaf_children1, leaf_node1 = next(generator)
        self.assertIn(leaf_node1, flat_children)
        self.assertEqual(len(leaf_children1), 0)
        self.assertEqual(len(leaf_parents1), 0)

        next_parents1, next_children1, next_node1 = next(generator)
        self.assertIn(next_node1, flat_parents)
        # duplicated parent from double grandparent
        self.assertEqual(len(next_children1), 2)
        self.assertEqual(len([p for p in next_parents1 if "tutorial_gui" in p.id]), 2)

        next_parents2, next_children2, next_node2 = next(generator)
        # going through next children now
        self.assertIn(next_node2, next_children1)
        # implicit_both clone was cloned already
        self.assertEqual(len(next_children2), 0)
        # parents are reused so no new parsed parents
        self.assertEqual(len([p for p in next_parents2 if "tutorial_gui" in p.id]), 0)
        next_parents3, next_children3, next_node3 = next(generator)
        # going through next children now
        self.assertIn(next_node3, next_children1)
        # implicit_both clone was cloned already
        self.assertEqual(len(next_children2), 0)
        # parents are reused so no new parsed parents
        self.assertEqual(len([p for p in next_parents2 if "tutorial_gui" in p.id]), 0)

    def test_shared_root_from_object_roots(self):
        """Test correct expectation of separately adding a shared root to a graph of disconnected object trees."""
        self.config["tests_str"] += "only tutorial3\n"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
            with_shared_root=False,
        )
        graph.parse_shared_root_from_object_roots(self.config["param_dict"])
        # assert one shared root exists and it connects all object roots
        shared_root_node = None
        for node in graph.nodes:
            if node.is_shared_root():
                if shared_root_node is not None:
                    raise AssertionError("More than one shared root nodes found in graph")
                shared_root_node = node
        if not shared_root_node:
            raise AssertionError("No shared root nodes found in graph")
        for node in graph.nodes:
            if node.is_object_root():
                self.assertEqual(list(node.setup_nodes.keys()), [shared_root_node])

    def test_graph_sanity(self):
        """Test generic usage of the complete test graph."""
        nodes, objects = TestGraph.parse_object_nodes(
            None, self.config["tests_str"],
            prefix=self.prefix,
            object_restrs=self.config["vm_strs"],
            params=self.config["param_dict"],
        )
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            prefix=self.prefix,
            object_restrs=self.config["vm_strs"],
            params=self.config["param_dict"],
            with_shared_root=False,
        )
        comparable_objects = [o for o in graph.objects if o.suffix not in ["net2", "net3", "net4", "net5"]]
        comparable_nodes = [n for n in graph.nodes if "a" not in n.prefix]

        # check prefixes and suffixes match
        self.assertEqual({o.suffix for o in comparable_objects}, {o.suffix for o in objects})
        self.assertEqual({n.prefix for n in comparable_nodes}, {n.prefix for n in nodes})

        # check all objects and nodes within the graph are unique
        for test_object in graph.objects:
            compare = lambda x, y: x.long_suffix == y.long_suffix if x.key == "images" else x.params["name"] == y.params["name"]
            self.assertEqual([test_object], [o for o in graph.objects if compare(o, test_object)])
            if test_object in comparable_objects:
                self.assertEqual([test_object.id], [o.id for o in comparable_objects if compare(o, test_object)])
        for test_node in graph.nodes:
            self.assertEqual([test_node], [n for n in graph.nodes if n.params["name"] == test_node.params["name"]])
            if test_node in comparable_nodes:
                self.assertEqual([test_node.id], [n.id for n in comparable_nodes if n.params["name"] == test_node.params["name"]])

        repr = str(graph)
        self.assertIn("[cartgraph]", repr)
        self.assertIn("[object]", repr)
        self.assertIn("[node]", repr)

    def test_traverse_one_leaf_parallel(self):
        """Test traversal path of one test without any reusable setup."""
        graph = self._load_for_parsing("normal..tutorial1",
                                       {"nets": " ".join([f"net{i+1}" for i in range(4)])})

        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.stateless.noop.vm1", "vms": "^vm1$", "type": "^shared_configure_install$"},
            {"shortname": "^original.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads.vm1", "vms": "^vm1$", "set_state_images": "^install$"},
            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$", "get_state_images": "^install$", "set_state_images": "^customize$"},
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "get_state_images": "^customize$", "set_state_vms": "^on_customize$"},
            {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "get_state_vms": "^on_customize$"},
        ]

        self._run_traversal(graph)

    def test_traverse_one_leaf_serial(self):
        """Test traversal path of one test without any reusable setup and with a serial unisolated run."""
        graph = self._load_for_parsing("normal..tutorial1", {"nets": "net0"})

        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.stateless.noop.vm1", "vms": "^vm1$", "type": "^shared_configure_install$", "nets_spawner": "process"},
            {"shortname": "^original.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads.vm1", "vms": "^vm1$", "nets_spawner": "process"},
            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$", "nets_spawner": "process"},
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "nets_spawner": "process"},
            {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "nets_spawner": "process"},
        ]

        self._run_traversal(graph)

    def test_traverse_one_leaf_with_setup(self):
        """Test traversal path of one test with a reusable setup."""
        graph = self._load_for_parsing("normal..tutorial1",
                                       {"nets": " ".join([f"net{i+1}" for i in range(3)])})

        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyTestRun.asserted_tests = [
            # cleanup is expected only if at least one of the states is reusable (here root+install)
            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$", "nets_spawner": "lxc", "nets": "^net1$"},
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "nets_spawner": "lxc", "nets": "^net1$"},
            {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "nets_spawner": "lxc", "nets": "^net1$"},
        ]

        self._run_traversal(graph)

    def test_traverse_one_leaf_with_step_setup(self):
        """Test traversal path of one test with a single reusable setup test node."""
        graph = self._load_for_parsing("normal..tutorial1",
                                       {"nets": " ".join([f"net{i+1}" for i in range(3)])})

        DummyStateControl.asserted_states["check"]["customize"][self.shared_pool] = True
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.stateless.noop.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^original.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "nets": "^net1$"},
        ]

        self._run_traversal(graph)

    def test_traverse_one_leaf_with_failed_setup(self):
        """Test traversal path of one test with a failed reusable setup test node."""
        graph = self._load_for_parsing("normal..tutorial1",
                                       {"nets": " ".join([f"net{i+1}" for i in range(2)])})

        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$", "nets": "^net1$", "_status": "FAIL"},
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "nets": "^net1$"},
        ]

        self._run_traversal(graph)

    def test_traverse_one_leaf_with_retried_setup(self):
        """Test traversal path of one test with a failed but retried setup test node."""
        graph = self._load_for_parsing("normal..tutorial1",
                                       {"nets": " ".join([f"net{i+1}" for i in range(4)])})

        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.stateless.noop.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^original.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads.vm1",
             "vms": "^vm1$", "nets": "^net1$", "_status": "FAIL"},
            {"shortname": "^internal.stateless.noop.vm1", "vms": "^vm1$"},
            {"shortname": "^original.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads.vm1",
             "vms": "^vm1$", "nets": "^net1$", "_status": "PASS"},
            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$", "nets": "^net1$", "_status": "FAIL"},
            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$", "nets": "^net1$", "_status": "FAIL"},
            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$", "nets": "^net1$", "_status": "PASS"},
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "nets": "^net1$"},
        ]

        self._run_traversal(graph, {"max_concurrent_tries": "1", "max_tries": "3", "stop_status": "pass"})

    def test_traverse_one_leaf_with_occupation_timeout(self):
        """Test multi-traversal of one test where it is occupied for too long (worker hangs)."""
        graph = TestGraph()
        graph.new_nodes(TestGraph.parse_flat_nodes("normal..tutorial1,normal..tutorial2"))
        # different order and restrictions so that we can emulate stuck net2
        graph.new_workers(TestGraph.parse_workers({"nets": "net1 net2 net4",
                                                   "only_vm1": "CentOS"}))
        graph.new_nodes(graph.parse_composite_nodes("normal..tutorial1", graph.workers["net2"].net))
        graph.new_nodes(graph.parse_composite_nodes("normal..tutorial2", graph.workers["net4"].net))
        graph.parse_shared_root_from_object_roots()

        test_node = graph.get_nodes(param_val="tutorial1.+net2", unique=True)
        test_node.started_worker = graph.workers["net2"]
        del graph.workers["net2"]
        test_node = graph.get_nodes(param_val="tutorial2.+net4", unique=True)
        test_node.started_worker = graph.workers["net4"]
        del graph.workers["net4"]
        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^normal.nongui.quicktest.tutorial2.files.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "nets": "^net1$"},
        ]

        self._run_traversal(graph, {"test_timeout": "1"})

    def test_traverse_two_objects_without_setup(self):
        """Test a two-object test traversal without a reusable setup."""
        graph = self._load_for_parsing("normal..tutorial3",
                                       {"nets": " ".join([f"net{i+1}" for i in range(4)])})

        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = False
        DummyStateControl.asserted_states["check"]["customize"][self.shared_pool] = False
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.stateless.noop.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^internal.stateless.noop.vm2", "vms": "^vm2$", "nets": "^net2$"},

            {"shortname": "^original.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^original.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads.vm2", "vms": "^vm2$", "nets": "^net2$"},

            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^internal.automated.customize.vm2", "vms": "^vm2$", "nets": "^net2$"},

            {"shortname": "^internal.automated.connect.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^normal.nongui.tutorial3", "vms": "^vm1 vm2$", "nets": "^net1$"},
        ]

        self._run_traversal(graph)
        # recreated setup is taken from the worker that created it (node reversal)
        self.assertLessEqual(DummyStateControl.asserted_states["get"]["install"][self.shared_pool], 2*4)
        self.assertLessEqual(DummyStateControl.asserted_states["get"]["customize"][self.shared_pool], 2*4)
        # recreated setup is taken from the worker that created it (node reversal)
        self.assertLessEqual(DummyStateControl.asserted_states["get"]["connect"][self.shared_pool], 1*4)

    def test_traverse_two_objects_with_setup(self):
        """Test a two-object test traversal with reusable setup."""
        graph = self._load_for_parsing("normal..tutorial3",
                                       {"nets": " ".join([f"net{i+1}" for i in range(4)])})

        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["customize"][self.shared_pool] = True
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.automated.connect.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^normal.nongui.tutorial3", "vms": "^vm1 vm2$", "nets": "^net1$"},
        ]

        self._run_traversal(graph)
        # get reusable setup from shared pool once to skip and once to sync (node reversal)
        self.assertLessEqual(DummyStateControl.asserted_states["get"]["install"][self.shared_pool], 2*4)
        self.assertLessEqual(DummyStateControl.asserted_states["get"]["customize"][self.shared_pool], 2*4)
        # recreated setup is taken from the worker that created it (node reversal)
        self.assertLessEqual(DummyStateControl.asserted_states["get"]["connect"][self.shared_pool], 2*4)

    def test_traverse_two_objects_with_shared_setup(self):
        """Test a two-object test traversal with shared setup among two nodes."""
        graph = self._load_for_parsing("leaves..tutorial_gui",
                                       {"nets": " ".join([f"net{i+1}" for i in range(4)])})

        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["customize"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["guisetup.noop"] = {self.shared_pool: False}
        DummyStateControl.asserted_states["check"]["guisetup.clicked"] = {self.shared_pool: False}
        DummyStateControl.asserted_states["get"]["guisetup.noop"] = {self.shared_pool: 0}
        DummyStateControl.asserted_states["get"]["guisetup.clicked"] = {self.shared_pool: 0}
        DummyStateControl.asserted_states["unset"] = {"guisetup.noop": {self.shared_pool: 0}}
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.automated.connect.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^normal.nongui.tutorial3", "vms": "^vm1 vm2$", "nets": "^net1$"},
        ]
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.automated.linux_virtuser.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^internal.automated.windows_virtuser.vm2", "vms": "^vm2$", "nets": "^net2$"},
            # net3 waits for net1 and net4 waits for net2, net1 then waits for net2 and net2 moves on
            {"shortname": "^leaves.tutorial_gui.client_clicked", "vms": "^vm1 vm2$", "nets": "^net2$"},
            {"shortname": "^leaves.tutorial_gui.client_noop", "vms": "^vm1 vm2$", "nets": "^net3$"},
        ]

        self._run_traversal(graph)
        for action in ["get"]:
            for state in ["install", "customize"]:
                # called once by worker for for each of two vms (no self-sync skip as setup is from previous run or shared pool)
                # NOTE: any such use cases assume the previous setup is fully synced across all workers, if this is not the case
                # it must be due to interrupted run in which case the setup is not guaranteed to be reusable on the first place
                self.assertLessEqual(DummyStateControl.asserted_states[action][state][self.shared_pool], 2*4)
        for action in ["set"]:
            for state in DummyStateControl.asserted_states[action]:
                self.assertEqual(DummyStateControl.asserted_states[action][state][self.shared_pool], 0)
        self.assertEqual(DummyStateControl.asserted_states["unset"]["guisetup.noop"][self.shared_pool], 1)

    def test_traverse_motif_with_flat_reuse(self):
        """Test that traversing a graph motif with flat node reused as setup works."""
        graph = self._load_for_parsing("leaves..client_clicked,leaves..explicit_clicked",
                                       {"nets": " ".join([f"net{i+1}" for i in range(2)])})

        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["customize"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["guisetup.clicked"] = {self.shared_pool: False}
        DummyStateControl.asserted_states["check"]["getsetup.clicked"] = {self.shared_pool: False}
        DummyStateControl.asserted_states["get"]["guisetup.clicked"] = {self.shared_pool: 0}
        DummyStateControl.asserted_states["get"]["getsetup.clicked"] = {self.shared_pool: 0}
        DummyStateControl.asserted_states["unset"] = {"guisetup.clicked": {self.shared_pool: 0}}
        DummyStateControl.asserted_states["unset"] = {"getsetup.clicked": {self.shared_pool: 0}}
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.automated.linux_virtuser.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^internal.automated.connect.vm1", "vms": "^vm1$", "nets": "^net2$"},
            {"shortname": "^internal.automated.windows_virtuser.vm2", "vms": "^vm2$", "nets": "^net1$"},
            {"shortname": "^leaves.tutorial_gui.client_clicked", "vms": "^vm1 vm2$", "nets": "^net1$"},
            {"shortname": "^leaves.tutorial_get.explicit_clicked.vm1", "vms": "^vm1 vm2 vm3$", "nets": "^net1$"},
        ]

        self._run_traversal(graph)
        for action in ["get"]:
            for state in ["install", "customize"]:
                # called once by worker for for each of two vms (no self-sync skip as setup is from previous run or shared pool)
                # NOTE: any such use cases assume the previous setup is fully synced across all workers, if this is not the case
                # it must be due to interrupted run in which case the setup is not guaranteed to be reusable on the first place
                self.assertLessEqual(DummyStateControl.asserted_states[action][state][self.shared_pool], 2*2)
        for action in ["set", "unset"]:
            for state in DummyStateControl.asserted_states[action]:
                self.assertEqual(DummyStateControl.asserted_states[action][state][self.shared_pool], 0)

    def test_traverse_motif_all(self):
        """Test that parsing and traversing works as expected with the largest possible sample graph."""
        self.job.config["vm_strs"] = {"only_vm1": "", "only_vm2": "", "only_vm3": ""}
        graph = self._load_for_parsing("leaves",
                                       {"nets": " ".join([f"net{i+1}" for i in range(2)])})

        # wrap within a mock to introduce delays
        graph.traverse_node = mock.MagicMock()
        graph.reverse_node = mock.MagicMock()
        # need to wait long enough to diversify picked nodes
        async def delayed_traverse_wrapper(*args, **kwards):
            test_node, worker = args[0], args[1]
            test_node.finished_worker = worker
            test_node.results = [{"name": "test", "status": "PASS", "time_elapsed": 3}]
            await asyncio.sleep(0.01)
        async def reverse_wrapper(*args, **kwards):
            pass
        graph.traverse_node.side_effect = delayed_traverse_wrapper
        graph.reverse_node.side_effect = reverse_wrapper

        DummyStateControl.asserted_states["check"].update({"getsetup": {self.shared_pool: False},
                                                           "guisetup.noop": {self.shared_pool: False}, "guisetup.clicked": {self.shared_pool: False},
                                                           "getsetup.noop": {self.shared_pool: False}, "getsetup.clicked": {self.shared_pool: False},
                                                           "getsetup.guisetup.noop": {self.shared_pool: False},
                                                           "getsetup.guisetup.clicked": {self.shared_pool: False}})
        DummyStateControl.asserted_states["get"].update({"getsetup": {self.shared_pool: 0},
                                                         "guisetup.noop": {self.shared_pool: 0}, "guisetup.clicked": {self.shared_pool: 0},
                                                         "getsetup.noop": {self.shared_pool: 0}, "getsetup.clicked": {self.shared_pool: 0},
                                                         "getsetup.guisetup.noop": {self.shared_pool: 0},
                                                         "getsetup.guisetup.clicked": {self.shared_pool: 0}})
        DummyStateControl.asserted_states["unset"] = {"guisetup.noop": {self.shared_pool: 0},
                                                      "getsetup.noop": {self.shared_pool: 0}}
        DummyTestRun.asserted_tests = [
        ]

        # need to wait long enough to diversify picked nodes
        self._run_traversal(graph)

    def test_overwrite_params_and_restrs(self):
        """Test for correct overwriting of default parameters and restrictions."""
        self.config["param_dict"]["nets"] = "net1"
        self.config["tests_str"] = "only leaves..explicit_clicked\n"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )
        default_object_param = graph.get_nodes(param_val="explicit_clicked", unique=True).params["images"]
        default_node_param = graph.get_nodes(param_val="explicit_clicked", unique=True).params["shared_pool"]
        custom_object_param1 = default_object_param + "01"
        custom_object_param2 = default_object_param + "02"
        custom_node_param = "remote:" + default_node_param

        self.config["param_dict"]["shared_pool"] = custom_node_param
        self.config["param_dict"]["new_key"] = "123"
        self.config["param_dict"]["images_vm1"] = custom_object_param1
        self.config["param_dict"]["images_vm2"] = custom_object_param2
        graph = self._load_for_parsing("leaves..explicit_clicked", {"nets": "net1"})

        # wrap within a mock to introduce delays
        graph.traverse_node = mock.MagicMock()
        graph.reverse_node = mock.MagicMock()
        async def traverse_wrapper(*args, **kwards):
            test_node, worker = args[0], args[1]
            test_node.finished_worker = worker
            test_node.results = [{"status": "PASS", "time_elapsed": 3}]
        async def reverse_wrapper(*args, **kwards):
            pass
        graph.traverse_node.side_effect = traverse_wrapper
        graph.reverse_node.side_effect = reverse_wrapper

        async def interrupted_wrapper(*args, **kwards):
            args[0].finished_worker = args[1]
            await asyncio.sleep(0.01)
        graph.traverse_node = mock.MagicMock()
        graph.traverse_node.side_effect = interrupted_wrapper
        graph.reverse_node = mock.MagicMock()
        graph.reverse_node.side_effect = interrupted_wrapper
        DummyStateControl.asserted_states["check"].update({"guisetup.noop": {self.shared_pool: False}, "guisetup.clicked": {self.shared_pool: False},
                                                           "getsetup.noop": {self.shared_pool: False}, "getsetup.clicked": {self.shared_pool: False},
                                                           "getsetup.guisetup.noop": {self.shared_pool: False},
                                                           "getsetup.guisetup.clicked": {self.shared_pool: False}})
        DummyTestRun.asserted_tests = [
        ]
        self._run_traversal(graph, params=self.config["param_dict"])

        test_node = graph.get_nodes(param_val="explicit_clicked.*net1", unique=True)
        self.assertNotEqual(test_node.params["shared_pool"], default_node_param,
                            "The default %s of %s wasn't overwritten" % (default_node_param, test_node.prefix))
        self.assertEqual(test_node.params["shared_pool"], custom_node_param,
                         "The new %s of %s must be %s" % (default_node_param, test_node.prefix, custom_node_param))
        self.assertEqual(test_node.params["new_key"], "123",
                         "A new parameter=%s of %s must be 123" % (test_node.params["new_key"], test_node.prefix))
        # TODO: the current suffix operators don't allow overwriting the suffix-free parameter default
        self.assertEqual(test_node.params["images"], default_object_param,
                         "The object-general default %s of %s must be overwritten" % (default_object_param, test_node.prefix))
        self.assertNotEqual(test_node.params["images_vm1"], default_object_param,
                            "The default %s of %s wasn't overwritten" % (default_object_param, test_node.prefix))
        self.assertEqual(test_node.params["images_vm1"], custom_object_param1,
                         "The new %s of %s must be %s" % (default_object_param, test_node.prefix, custom_object_param2))
        self.assertNotEqual(test_node.params["images_vm2"], default_object_param,
                            "The default %s of %s wasn't overwritten" % (default_object_param, test_node.prefix))
        self.assertEqual(test_node.params["images_vm2"], custom_object_param2,
                         "The new %s of %s must be %s" % (default_object_param, test_node.prefix, custom_object_param2))
        self.assertNotIn("images_vm3", test_node.params,
                         "The third vm of %s should use default images" % (test_node.prefix))

        test_objects = graph.get_objects(param_val="vm1.*CentOS")
        vm_objects = [o for o in test_objects if o.key == "vms"]
        self.assertEqual(len(vm_objects), 1, "There must be exactly one vm1 object")
        test_object1 = vm_objects[0]
        test_object_params1 = test_object1.params.object_params(test_object1.suffix)
        self.assertEqual(test_object_params1["new_key"], "123",
                         "A new parameter=%s of %s must be 123" % (test_object_params1["new_key"], test_object1.suffix))
        self.assertNotEqual(test_object_params1["images"], default_object_param,
                            "The default %s of %s wasn't overwritten" % (default_object_param, test_object1.suffix))
        self.assertEqual(test_object_params1["images"], custom_object_param1,
                         "The new %s of %s must be %s" % (default_object_param, test_object1.suffix, custom_object_param1))

        test_objects = graph.get_objects(param_val="vm2.*Win10")
        vm_objects = [o for o in test_objects if o.key == "vms"]
        self.assertEqual(len(vm_objects), 1, "There must be exactly one vm object for tutorial1")
        test_object2 = vm_objects[0]
        test_object_params2 = test_object2.params.object_params(test_object2.suffix)
        self.assertEqual(test_object_params1["new_key"], "123",
                         "A new parameter=%s of %s must be 123" % (test_object_params1["new_key"], test_object1.suffix))
        self.assertNotEqual(test_object_params2["images"], default_object_param,
                            "The default %s of %s wasn't overwritten" % (default_object_param, test_object2.suffix))
        self.assertEqual(test_object_params2["images"], custom_object_param2,
                         "The new %s of %s must be %s" % (default_object_param, test_object2.suffix, custom_object_param2))

    def test_overwrite_params_and_restrs_preparsed(self):
        """Test for correct overwriting of default parameters and restrictions in a preparsed graph."""
        self.config["param_dict"]["nets"] = "net1"
        self.config["tests_str"] = "only leaves..explicit_clicked\n"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )
        default_object_param = graph.get_nodes(param_val="explicit_clicked", unique=True).params["images"]
        default_node_param = graph.get_nodes(param_val="explicit_clicked", unique=True).params["shared_pool"]
        custom_object_param1 = default_object_param + "01"
        custom_object_param2 = default_object_param + "02"
        custom_node_param = "remote:" + default_node_param

        self.config["param_dict"]["shared_pool"] = custom_node_param
        self.config["param_dict"]["new_key"] = "123"
        self.config["param_dict"]["images_vm1"] = custom_object_param1
        self.config["param_dict"]["images_vm2"] = custom_object_param2
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )

        test_node = graph.get_nodes(param_val="explicit_clicked", unique=True)
        self.assertNotEqual(test_node.params["shared_pool"], default_node_param,
                            "The default %s of %s wasn't overwritten" % (default_node_param, test_node.prefix))
        self.assertEqual(test_node.params["shared_pool"], custom_node_param,
                         "The new %s of %s must be %s" % (default_node_param, test_node.prefix, custom_node_param))
        self.assertEqual(test_node.params["new_key"], "123",
                         "A new parameter=%s of %s must be 123" % (test_node.params["new_key"], test_node.prefix))
        # TODO: the current suffix operators don't allow overwriting the suffix-free parameter default
        self.assertEqual(test_node.params["images"], default_object_param,
                         "The object-general default %s of %s must be overwritten" % (default_object_param, test_node.prefix))
        self.assertNotEqual(test_node.params["images_vm1"], default_object_param,
                            "The default %s of %s wasn't overwritten" % (default_object_param, test_node.prefix))
        self.assertEqual(test_node.params["images_vm1"], custom_object_param1,
                         "The new %s of %s must be %s" % (default_object_param, test_node.prefix, custom_object_param2))
        self.assertNotEqual(test_node.params["images_vm2"], default_object_param,
                            "The default %s of %s wasn't overwritten" % (default_object_param, test_node.prefix))
        self.assertEqual(test_node.params["images_vm2"], custom_object_param2,
                         "The new %s of %s must be %s" % (default_object_param, test_node.prefix, custom_object_param2))
        self.assertNotIn("images_vm3", test_node.params,
                         "The third vm of %s should use default images" % (test_node.prefix))

        test_objects = graph.get_objects(param_val="vm1")
        vm_objects = [o for o in test_objects if o.key == "vms"]
        self.assertEqual(len(vm_objects), 1, "There must be exactly one vm1 object")
        test_object1 = vm_objects[0]
        test_object_params1 = test_object1.params.object_params(test_object1.suffix)
        self.assertEqual(test_object_params1["new_key"], "123",
                         "A new parameter=%s of %s must be 123" % (test_object_params1["new_key"], test_object1.suffix))
        self.assertNotEqual(test_object_params1["images"], default_object_param,
                            "The default %s of %s wasn't overwritten" % (default_object_param, test_object1.suffix))
        self.assertEqual(test_object_params1["images"], custom_object_param1,
                         "The new %s of %s must be %s" % (default_object_param, test_object1.suffix, custom_object_param1))

        test_objects = graph.get_objects(param_val="vm2")
        vm_objects = [o for o in test_objects if o.key == "vms"]
        self.assertEqual(len(vm_objects), 1, "There must be exactly one vm object for tutorial1")
        test_object2 = vm_objects[0]
        test_object_params2 = test_object2.params.object_params(test_object2.suffix)
        self.assertEqual(test_object_params1["new_key"], "123",
                         "A new parameter=%s of %s must be 123" % (test_object_params1["new_key"], test_object1.suffix))
        self.assertNotEqual(test_object_params2["images"], default_object_param,
                            "The default %s of %s wasn't overwritten" % (default_object_param, test_object2.suffix))
        self.assertEqual(test_object_params2["images"], custom_object_param2,
                         "The new %s of %s must be %s" % (default_object_param, test_object2.suffix, custom_object_param2))

    def test_run_warn_duration(self):
        """Test that a good test status is converted to warning if test takes too long."""
        self.config["tests_str"] += "only tutorial1\n"

        flat_net = TestGraph.parse_net_from_object_restrs("net1", self.config["vm_strs"])
        test_objects = TestGraph.parse_components_for_object(flat_net, "nets", params=self.config["param_dict"], unflatten=True)
        net = test_objects[-1]
        test_node = TestGraph.parse_node_from_object(net, "normal..tutorial1", params=self.config["param_dict"].copy())

        test_node.results = [{"status": "PASS", "time_elapsed": 3}]
        DummyTestRun.asserted_tests = [
            {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "_status": "PASS", "_time_elapsed": "10"},
        ]
        test_node.started_worker = "some-worker-since-only-traversal-allowed"
        to_run = self.runner.run_test_node(test_node)
        status = self.runner.loop.run_until_complete(asyncio.wait_for(to_run, None))
        self.assertTrue(status)
        # the test succeed but too long so its status must be changed to WARN
        self.assertEqual(test_node.results[-1]["status"], "WARN")
        self.assertEqual(len(DummyTestRun.asserted_tests), 0, "Some tests weren't run: %s" % DummyTestRun.asserted_tests)

    def test_run_exit_code(self):
        """Test that the test status is properly converted to a simple exit status."""
        self.config["tests_str"] += "only tutorial1\n"
        flat_net = TestGraph.parse_net_from_object_restrs("net1", self.config["vm_strs"])
        test_objects = TestGraph.parse_components_for_object(flat_net, "nets", params=self.config["param_dict"], unflatten=True)
        net = test_objects[-1]

        test_node = TestGraph.parse_node_from_object(net, "normal..tutorial1", params=self.config["param_dict"].copy())
        DummyTestRun.asserted_tests = [
            {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "_status" : "FAIL"},
            {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "_status" : "PASS"},
        ]
        test_node.started_worker = "some-worker-since-only-traversal-allowed"

        to_run = self.runner.run_test_node(test_node)
        status = self.runner.loop.run_until_complete(asyncio.wait_for(to_run, None))
        # the run failed - status must be False
        self.assertFalse(status)
        self.assertFalse(self.runner.all_results_ok())

        to_run = self.runner.run_test_node(test_node)
        status = self.runner.loop.run_until_complete(asyncio.wait_for(to_run, None))
        # new run of same test passed - status must be True
        self.assertTrue(status, "Runner did not preserve last run fail status")
        self.assertTrue(self.runner.all_results_ok())

        self.assertEqual(len(DummyTestRun.asserted_tests), 0, "Some tests weren't run: %s" % DummyTestRun.asserted_tests)
        DummyTestRun.asserted_tests = [
            {"shortname": "^normal.nongui.quicktest.tutorial2.files.vm1", "vms": "^vm1$", "_status" : "FAIL"},
            {"shortname": "^normal.nongui.quicktest.tutorial2.files.vm1", "vms": "^vm1$", "_status" : "PASS"},
        ]
        test_node = TestGraph.parse_node_from_object(net, "normal..tutorial2.files", params=self.config["param_dict"].copy())
        test_node.started_worker = "some-worker-since-only-traversal-allowed"

        to_run = self.runner.run_test_node(test_node)
        status = self.runner.loop.run_until_complete(asyncio.wait_for(to_run, None))
        # run of second test failed - status must be False
        self.assertFalse(status)
        self.assertFalse(self.runner.all_results_ok())

        to_run = self.runner.run_test_node(test_node)
        status = self.runner.loop.run_until_complete(asyncio.wait_for(to_run, None))
        # new run of second test passed - status must be True
        self.assertTrue(status, "Runner did not preserve last run fail status")
        self.assertTrue(self.runner.all_results_ok())

    def test_rerun_max_times_serial(self):
        """Test that the test is tried `max_tries` times if no status is not specified."""
        self.config["tests_str"] += "only tutorial1\n"
        self.config["param_dict"]["max_tries"] = "3"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            "", self.config["vm_strs"],
            self.config["param_dict"],
        )
        DummyTestRun.asserted_tests = [
            {"shortname": r"^internal.stateless.noop.vm1", "vms": r"^vm1$"},
            {"shortname": r"^original.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads.vm1", "vms": r"^vm1$"},
            {"shortname": r"^internal.stateless.noop.vm1", "vms": r"^vm1$"},
            {"shortname": r"^original.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads.vm1", "vms": r"^vm1$"},
            {"shortname": r"^internal.stateless.noop.vm1", "vms": r"^vm1$"},
            {"shortname": r"^original.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads.vm1", "vms": r"^vm1$"},
            {"shortname": r"^internal.automated.customize.vm1", "vms": r"^vm1$"},
            {"shortname": r"^internal.automated.customize.vm1", "vms": r"^vm1$", "_long_prefix": r"^[a\d]+r1-vm1$"},
            {"shortname": r"^internal.automated.customize.vm1", "vms": r"^vm1$", "_long_prefix": r"^[a\d]+r2-vm1$"},
            {"shortname": r"^internal.automated.on_customize.vm1", "vms": r"^vm1$"},
            {"shortname": r"^internal.automated.on_customize.vm1", "vms": r"^vm1$", "_long_prefix": r"^[a\d]+r1-vm1$"},
            {"shortname": r"^internal.automated.on_customize.vm1", "vms": r"^vm1$", "_long_prefix": r"^[a\d]+r2-vm1$"},
            {"shortname": r"^normal.nongui.quicktest.tutorial1.vm1", "vms": r"^vm1$"},
            {"shortname": r"^normal.nongui.quicktest.tutorial1.vm1", "vms": r"^vm1$", "_long_prefix": r"^[a\d]+r1-vm1$"},
            {"shortname": r"^normal.nongui.quicktest.tutorial1.vm1", "vms": r"^vm1$", "_long_prefix": r"^[a\d]+r2-vm1$"},
        ]
        self._run_traversal(graph)

    def test_rerun_max_times_parallel(self):
        """Test that the test is tried `max_tries` times if no status is not specified."""
        self.config["tests_str"] += "only tutorial1\n"
        self.config["param_dict"]["max_tries"] = "3"
        self.config["param_dict"]["nets"] = "net1 net2"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            "", self.config["vm_strs"],
            self.config["param_dict"],
        )
        DummyStateControl.asserted_states["check"] = {"root": {self.shared_pool: True}, "install": {self.shared_pool: True},
                                                      "customize": {self.shared_pool: True}, "on_customize": {self.shared_pool: True}}
        DummyTestRun.asserted_tests = [
            {"shortname": r"^normal.nongui.quicktest.tutorial1.vm1", "vms": r"^vm1$", "nets": "^net1$"},
            {"shortname": r"^normal.nongui.quicktest.tutorial1.vm1", "vms": r"^vm1$", "_long_prefix": r"^[a\d]+r1-vm1$", "nets": "^net2$"},
            {"shortname": r"^normal.nongui.quicktest.tutorial1.vm1", "vms": r"^vm1$", "_long_prefix": r"^[a\d]+r2-vm1$", "nets": "^net1$"},
        ]
        self._run_traversal(graph)

    def test_rerun_status_times(self):
        """Test that valid statuses are considered when retrying a test."""
        self.config["tests_str"] += "only tutorial1\n"
        self.config["param_dict"]["nets"] = "net1"
        self.config["param_dict"]["max_tries"] = "4"
        self.config["param_dict"]["stop_status"] = ""

        # test should be re-run on these statuses
        for status in ["PASS", "WARN", "FAIL", "ERROR", "SKIP", "INTERRUPTED", "CANCEL"]:
            with self.subTest(f"Test rerun on status {status}"):
                graph = TestGraph.parse_object_trees(
                    None, self.config["tests_str"],
                    self.prefix, self.config["vm_strs"],
                    self.config["param_dict"],
                )
                DummyStateControl.asserted_states["check"] = {"root": {self.shared_pool: True}, "install": {self.shared_pool: True},
                                                              "customize": {self.shared_pool: True}, "on_customize": {self.shared_pool: True}}
                DummyTestRun.asserted_tests = [
                    {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "_status" : status},
                    {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "_status" : status},
                    {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "_status" : status},
                    {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "_status" : status},
                ]
                self._run_traversal(graph)

                # assert that tests were repeated
                self.assertEqual(len(self.runner.job.result.tests), 4)
                self.assertEqual(len(graph.get_nodes(param_val="tutorial1", unique=True).results), 4)
                # also assert the correct results were registered
                self.assertEqual([x["status"] for x in self.runner.job.result.tests], [status] * 4)
                registered_results = []
                for result in self.runner.job.result.tests:
                    result["name"] = result["name"].name
                    registered_results.append(result)
                self.assertEqual(registered_results, graph.get_nodes(param_val="tutorial1", unique=True).results)
                # the test graph and thus the test node is recreated
                self.runner.job.result.tests.clear()

    def test_rerun_status_stop(self):
        """Test that the `stop_status` parameter lets the traversal continue as usual."""
        self.config["tests_str"] += "only tutorial1\n"
        self.config["param_dict"]["nets"] = "net1"
        self.config["param_dict"]["max_tries"] = "3"

        # expect success and get success -> should run only once
        for stop_status in ["pass", "warn", "fail", "error"]:
            with self.subTest(f"Test rerun stop on status {stop_status}"):
                self.config["param_dict"]["stop_status"] = stop_status
                status = stop_status.upper()
                graph = TestGraph.parse_object_trees(
                    None, self.config["tests_str"],
                    self.prefix, self.config["vm_strs"],
                    self.config["param_dict"],
                )
                DummyStateControl.asserted_states["check"] = {"root": {self.shared_pool: True}, "install": {self.shared_pool: True},
                                                              "customize": {self.shared_pool: True}, "on_customize": {self.shared_pool: True}}
                DummyTestRun.asserted_tests = [
                    {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "_status" : status},
                ]
                self._run_traversal(graph)

                # assert that tests were not repeated
                self.assertEqual(len(self.runner.job.result.tests), 1)
                self.assertEqual(len(graph.get_nodes(param_val="tutorial1", unique=True).results), 1)
                # also assert the correct results were registered
                self.assertEqual([x["status"] for x in self.runner.job.result.tests], [status])
                registered_results = []
                for result in self.runner.job.result.tests:
                    result["name"] = result["name"].name
                    registered_results.append(result)
                self.assertEqual(registered_results, graph.get_nodes(param_val="tutorial1", unique=True).results)
                # the test graph and thus the test node is recreated
                self.runner.job.result.tests.clear()

    def test_rerun_status_rerun(self):
        """Test that the `rerun_status` parameter keep the traversal repeating a run."""
        self.config["tests_str"] += "only tutorial1\n"
        self.config["param_dict"]["nets"] = "net1"
        self.config["param_dict"]["max_tries"] = "3"

        # expect success and get success -> should run only once
        for stop_status in ["pass", "warn", "fail", "error"]:
            with self.subTest(f"Test rerun stop on status {stop_status}"):
                self.config["param_dict"]["rerun_status"] = stop_status
                status = stop_status.upper()
                graph = TestGraph.parse_object_trees(
                    None, self.config["tests_str"],
                    self.prefix, self.config["vm_strs"],
                    self.config["param_dict"],
                )
                DummyStateControl.asserted_states["check"] = {"root": {self.shared_pool: True}, "install": {self.shared_pool: True},
                                                              "customize": {self.shared_pool: True}, "on_customize": {self.shared_pool: True}}
                DummyTestRun.asserted_tests = [
                    {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "_status" : status},
                    {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "_status" : "INTERRUPTED"},
                ]
                self._run_traversal(graph)

                # assert that tests were not repeated
                self.assertEqual(len(self.runner.job.result.tests), 2)
                self.assertEqual(len(graph.get_nodes(param_val="tutorial1", unique=True).results), 2)
                # also assert the correct results were registered
                self.assertEqual([x["status"] for x in self.runner.job.result.tests], [status, "INTERRUPTED"])
                registered_results = []
                for result in self.runner.job.result.tests:
                    result["name"] = result["name"].name
                    registered_results.append(result)
                self.assertEqual(registered_results, graph.get_nodes(param_val="tutorial1", unique=True).results)
                # the test graph and thus the test node is recreated
                self.runner.job.result.tests.clear()

    def test_rerun_previous_job_default(self):
        """Test that rerunning a previous job gives more tries and works as expected."""
        # need proper previous results from full nodes (possibly different worker and set variant)
        self.config["param_dict"] = {"nets": "net2"}
        self.config["tests_str"] = "only leaves..tutorial2\n"
        self.config["vm_strs"]["vm1"] = ""
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )
        node11, node12, node21, node22 = graph.get_nodes(param_val="tutorial2")
        # results from the previous job (inclusive of setup that should now be skipped)
        on_customize_tests = [n.params["name"] for n in graph.get_nodes(param_val="on_customize")]
        self.assertEqual(len(on_customize_tests), 2)
        self.runner.previous_results += [{"name": on_customize_tests[0], "status": "PASS", "time_elapsed": 1}]
        self.runner.previous_results += [{"name": on_customize_tests[1], "status": "PASS", "time_elapsed": 1}]
        self.runner.previous_results += [{"name": node11.params["name"], "status": "PASS", "time_elapsed": 1}]
        self.runner.previous_results += [{"name": node12.params["name"], "status": "FAIL", "time_elapsed": 0.2}]
        self.runner.previous_results += [{"name": node21.params["name"].replace("leaves", "all"), "status": "FAIL", "time_elapsed": 0.2}]
        self.runner.previous_results += [{"name": node22.params["name"].replace("leaves", "all"), "status": "PASS", "time_elapsed": 1}]

        # include flat and other types of nodes by traversing partially parsed graph
        graph = TestGraph()
        graph.new_nodes(TestGraph.parse_flat_nodes("leaves..tutorial2"))
        graph.parse_shared_root_from_object_roots()
        graph.new_workers(TestGraph.parse_workers({"nets": "net1", "only_vm1": ""}))
        DummyStateControl.asserted_states["check"] = {"root": {self.shared_pool: True}, "install": {self.shared_pool: True},
                                                      "customize": {self.shared_pool: True}, "on_customize": {self.shared_pool: True}}
        DummyTestRun.asserted_tests = [
            # skip the previously passed test since it doesn't have a rerun status (here fail by default) and rerun second test
            {"shortname": "^leaves.quicktest.tutorial2.names.vm1.+CentOS", "vms": "^vm1$"},
            # skip the previously passed test since it doesn't have a rerun status (here fail by default) and rerun second test
            {"shortname": "^leaves.quicktest.tutorial2.files.vm1.+Fedora", "vms": "^vm1$"},
        ]
        self._run_traversal(graph, {"replay": "previous_job"})

        node11, node12, node21, node22 = graph.get_nodes(param_val="tutorial2.+vm1")
        # assert that tests were repeated only when needed
        self.assertEqual(len(self.runner.job.result.tests), 2)
        self.assertEqual(len(node11.results), 1)
        self.assertEqual(len(node12.results), 2)
        self.assertEqual(len(node21.results), 2)
        self.assertEqual(len(node22.results), 1)
        # also assert the correct results were registered
        self.assertEqual([x["status"] for x in self.runner.job.result.tests], ["PASS", "PASS"])
        self.assertEqual([x["status"] for x in node11.results], ["PASS"])
        self.assertEqual([x["status"] for x in node12.results], ["FAIL", "PASS"])
        self.assertEqual([x["status"] for x in node21.results], ["FAIL", "PASS"])
        self.assertEqual([x["status"] for x in node22.results], ["PASS"])
        registered_results = []
        for result in self.runner.job.result.tests:
            result["name"] = result["name"].name
            registered_results.append(result)
        self.assertEqual(registered_results, node21.results[1:] + node12.results[1:])

    def test_rerun_previous_job_status(self):
        """Test that rerunning a previous job on a given status works as expected."""
        # need proper previous results from full nodes
        self.config["param_dict"] = {"nets": "net1"}
        self.config["tests_str"] = "only leaves..tutorial2\n"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )
        node1, node2 = graph.get_nodes(param_val="tutorial2")
        # results from the previous job (inclusive of setup that should now be skipped)
        self.runner.previous_results += [{"name": graph.get_nodes(param_val="on_customize", unique=True).params["name"], "status": "PASS", "time_elapsed": 1}]
        self.runner.previous_results += [{"name": node1.params["name"], "status": "PASS", "time_elapsed": 1}]
        self.runner.previous_results += [{"name": node2.params["name"], "status": "FAIL", "time_elapsed": 0.2}]

        # include flat and other types of nodes by traversing partially parsed graph
        graph = TestGraph()
        graph.new_nodes(TestGraph.parse_flat_nodes("leaves..tutorial2"))
        graph.parse_shared_root_from_object_roots()
        graph.new_workers(TestGraph.parse_workers({"nets": "net1", "only_vm1": "CentOS"}))
        DummyStateControl.asserted_states["check"] = {"root": {self.shared_pool: True}, "install": {self.shared_pool: True},
                                                      "customize": {self.shared_pool: True}, "on_customize": {self.shared_pool: True}}
        DummyTestRun.asserted_tests = [
            # previously run setup tests with rerun status are still rerun (scan is overriden)
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "get_state_images": "^customize$", "set_state_vms": "^on_customize$"},
            # skip the previously failed second test since it doesn't have a rerun status and rerun first test
            {"shortname": "^leaves.quicktest.tutorial2.files.vm1", "vms": "^vm1$"},
        ]
        self._run_traversal(graph, {"replay": "previous_job", "rerun_status": "pass"})

        node1, node2 = graph.get_nodes(param_val="tutorial2.+vm1")
        # assert that tests were repeated only when needed
        self.assertEqual(len(self.runner.job.result.tests), 2)
        self.assertEqual(len(node1.results), 2)
        self.assertEqual(len(node2.results), 1)
        # also assert the correct results were registered
        self.assertEqual([x["status"] for x in self.runner.job.result.tests], ["PASS", "PASS"])
        self.assertEqual([x["status"] for x in node1.results], ["PASS", "PASS"])
        self.assertEqual([x["status"] for x in node2.results], ["FAIL"])
        registered_results = []
        for result in self.runner.job.result.tests:
            result["name"] = result["name"].name
            registered_results.append(result)
        self.assertEqual(registered_results[1:], node1.results[1:])

    def test_rerun_invalid(self):
        """Test if an exception is thrown with invalid retry parameter values."""
        self.config["tests_str"] += "only tutorial1\n"
        DummyStateControl.asserted_states["check"] = {"root": {self.shared_pool: True}, "install": {self.shared_pool: True},
                                                      "customize": {self.shared_pool: True}, "on_customize": {self.shared_pool: True}}

        DummyTestRun.asserted_tests = [
                    {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$"},
        ]
        with mock.patch.dict(self.config["param_dict"], {"max_tries": "3",
                                                         "stop_status": "invalid"}):
            graph = TestGraph.parse_object_trees(
                None, self.config["tests_str"],
                self.prefix, self.config["vm_strs"],
                self.config["param_dict"],
            )
            with self.assertRaisesRegex(ValueError, r"^Value of stop status must be a valid test status"):
                self._run_traversal(graph)

        # negative values
        DummyTestRun.asserted_tests = [
                    {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$"},
        ]
        with mock.patch.dict(self.config["param_dict"], {"max_tries": "-32",
                                                         "stop_status": ""}):
            graph = TestGraph.parse_object_trees(
                None, self.config["tests_str"],
                self.prefix, self.config["vm_strs"],
                self.config["param_dict"],
            )
            with self.assertRaisesRegex(ValueError, r"^Number of max_tries cannot be less than zero$"):
                self._run_traversal(graph)

        # floats
        DummyTestRun.asserted_tests = [
                    {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$"},
        ]
        with mock.patch.dict(self.config["param_dict"], {"max_tries": "3.5",
                                                         "stop_status": ""}):
            graph = TestGraph.parse_object_trees(
                None, self.config["tests_str"],
                self.prefix, self.config["vm_strs"],
                self.config["param_dict"],
            )
            with self.assertRaisesRegex(ValueError, r"^invalid literal for int"):
                self._run_traversal(graph)

        # non-integers
        DummyTestRun.asserted_tests = [
                    {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$"},
        ]
        with mock.patch.dict(self.config["param_dict"], {"max_tries": "hey",
                                                         "stop_status": ""}):
            graph = TestGraph.parse_object_trees(
                None, self.config["tests_str"],
                self.prefix, self.config["vm_strs"],
                self.config["param_dict"],
            )
            with self.assertRaisesRegex(ValueError, r"^invalid literal for int"):
                self._run_traversal(graph)

    def test_dry_run(self):
        """Test a complete dry run traversal of a graph."""
        # TODO: cannot parse "all" with flat nodes with largest available test set being "leaves"
        graph = self._load_for_parsing("leaves", {"nets": " ".join([f"net{i+1}" for i in range(3)])})

        DummyStateControl.asserted_states["check"].update({"guisetup.noop": {self.shared_pool: False}, "guisetup.clicked": {self.shared_pool: False},
                                                           "getsetup.noop": {self.shared_pool: False}, "getsetup.clicked": {self.shared_pool: False},
                                                           "getsetup.guisetup.noop": {self.shared_pool: False},
                                                           "getsetup.guisetup.clicked": {self.shared_pool: False}})
        DummyTestRun.asserted_tests = [
        ]

        self._run_traversal(graph, {"dry_run": "yes"})
        for action in ["get", "set", "unset"]:
            for state in DummyStateControl.asserted_states[action]:
                self.assertEqual(DummyStateControl.asserted_states[action][state][self.shared_pool], 0)

    def test_aborted_run(self):
        """Test that traversal is aborted through explicit configuration."""
        graph = self._load_for_parsing("tutorial1", {"nets": " ".join([f"net{i+1}" for i in range(3)])})

        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$"},
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "set_state_vms_on_error": "^$", "_status": "FAIL"},
        ]

        with self.assertRaisesRegex(exceptions.TestSkipError, r"^God wanted this test to abort$"):
            self._run_traversal(graph, {"abort_on_error": "yes"})

    def test_parsing_on_demand(self):
        """Test that parsing on demand works as expected."""
        # make sure to parse flat nodes (with CentOS restriction) that will never be composed with any compatible objects
        graph = self._load_for_parsing("leaves",
                                       {"nets": " ".join([f"net{i+1}" for i in range(2)]),
                                        # TODO: this only overwrites the nets with no only restrictions predefined (no net3)
                                        "only_vm1": "Fedora"})

        # wrap within a mock as a spy option
        actual_parsing = graph.parse_paths_to_object_roots
        graph.parse_paths_to_object_roots = mock.MagicMock()
        graph.parse_paths_to_object_roots.side_effect = actual_parsing
        async def interrupted_wrapper(*args, **kwards):
            await asyncio.sleep(0.01)
        graph.traverse_node = mock.MagicMock()
        graph.traverse_node.side_effect = interrupted_wrapper
        graph.reverse_node = mock.MagicMock()
        graph.reverse_node.side_effect = interrupted_wrapper

        DummyStateControl.asserted_states["check"].update({"guisetup.noop": {self.shared_pool: False}, "guisetup.clicked": {self.shared_pool: False},
                                                           "getsetup.noop": {self.shared_pool: False}, "getsetup.clicked": {self.shared_pool: False},
                                                           "getsetup.guisetup.noop": {self.shared_pool: False},
                                                           "getsetup.guisetup.clicked": {self.shared_pool: False}})
        DummyTestRun.asserted_tests = [
        ]

        self._run_traversal(graph)

        # the graph has a specific connectedness with the shared root
        shared_roots = graph.get_nodes("shared_root", "yes")
        assert len(shared_roots) == 1, "There can be only exactly one starting node (shared root)"
        root = shared_roots[0]
        for node in graph.nodes:
            if node in root.cleanup_nodes:
                self.assertTrue(node.is_flat() or node.is_object_root())
        # all flat nodes but the shared root must be unrolled once and must have parsed paths
        flat_nodes = [node for node in graph.nodes if node.is_flat()]
        self.assertEqual(graph.parse_paths_to_object_roots.call_count, (len(flat_nodes) - 1) * 2)
        for node in flat_nodes:
            parse_calls = [mock.call(node, w.net, mock.ANY) for w in graph.workers.values()]
            for i in range(2):
                worker = graph.workers[f"net{i+1}"]
                self.assertTrue(node.is_unrolled())
                if node == root:
                    self.assertNotIn(mock.call(node, worker.net, mock.ANY),
                                     graph.parse_paths_to_object_roots.call_args_list)
                else:
                    self.assertFalse(node.is_shared_root())
                    self.assertTrue(parse_calls[0] in graph.parse_paths_to_object_roots.call_args_list or
                                    parse_calls[1] in graph.parse_paths_to_object_roots.call_args_list)

        # check flat nodes that could never be composed (not compatible with vm1 restriction)
        flat_residue = graph.get_nodes_by_name("tutorial3.remote")
        self.assertEqual(len(flat_residue), 16)
        for node in flat_residue:
            self.assertNotEqual(node.incompatible_workers & {"net1", "net2"}, set())

    def test_traversing_in_isolation(self):
        """Test that actual traversing (not just test running) works as expected."""
        graph = self._load_for_parsing("leaves", {"nets": " ".join([f"net{i+1}" for i in range(3)])})

        # wrap within a mock as a spy option
        actual_traversing = graph.traverse_node
        actual_reversing = graph.reverse_node
        graph.traverse_node = mock.MagicMock()
        graph.traverse_node.side_effect = actual_traversing
        graph.reverse_node = mock.MagicMock()
        graph.reverse_node.side_effect = actual_reversing

        DummyStateControl.asserted_states["check"].update({"guisetup.noop": {self.shared_pool: False}, "guisetup.clicked": {self.shared_pool: False},
                                                           "getsetup.noop": {self.shared_pool: False}, "getsetup.clicked": {self.shared_pool: False},
                                                           "getsetup.guisetup.noop": {self.shared_pool: False},
                                                           "getsetup.guisetup.clicked": {self.shared_pool: False}})
        DummyTestRun.asserted_tests = [
        ]

        self._run_traversal(graph, {"dry_run": "yes"})

        traverse_calls = graph.traverse_node.call_args_list
        reverse_calls = graph.reverse_node.call_args_list
        for node in graph.nodes:
            # shared root will be checked in the end with separate expectations
            if node.is_shared_root():
                continue
            picked_by_setup = node._picked_by_setup_nodes
            picked_by_cleanup = node._picked_by_cleanup_nodes
            dropped_setup = node._dropped_setup_nodes
            dropped_cleanup = node._dropped_cleanup_nodes
            # the three workers comprise all possible visits of the node in the four registers
            self.assertEqual(picked_by_setup.get_counters(),
                             sum(picked_by_setup.get_counters(worker=w) for w in graph.workers.values()))
            self.assertEqual(picked_by_cleanup.get_counters(),
                             sum(picked_by_cleanup.get_counters(worker=w) for w in graph.workers.values()))
            self.assertEqual(dropped_setup.get_counters(),
                             sum(dropped_setup.get_counters(worker=w) for w in graph.workers.values()))
            self.assertEqual(dropped_cleanup.get_counters(),
                             sum(dropped_cleanup.get_counters(worker=w) for w in graph.workers.values()))
            for worker in graph.workers.values():
                if worker.id not in ["net1", "net2", "net3"]:
                    continue
                # consider only workers relevant to the current checked node
                if not node.is_flat() and worker.id not in node.params["name"]:
                    continue
                # the worker relevant nodes comprise all possible visits by that worker
                worker_setup = [n for n in node.setup_nodes if n.is_flat() or worker.id in n.params["name"]]
                worker_cleanup = [n for n in node.cleanup_nodes if n.is_flat() or worker.id in n.params["name"]]
                self.assertEqual(picked_by_setup.get_counters(worker=worker),
                                sum(picked_by_setup.get_counters(n, worker=worker) for n in worker_setup))
                self.assertEqual(picked_by_cleanup.get_counters(worker=worker),
                                sum(picked_by_cleanup.get_counters(n, worker=worker) for n in worker_cleanup))
                self.assertEqual(dropped_setup.get_counters(worker=worker),
                                sum(dropped_setup.get_counters(n, worker=worker) for n in worker_setup))
                self.assertEqual(dropped_cleanup.get_counters(worker=worker),
                                sum(dropped_cleanup.get_counters(n, worker=worker) for n in worker_cleanup))

                picked_counter = {s: s._picked_by_cleanup_nodes.get_counters(node=node, worker=worker) for s in worker_setup}
                average_picked_counter = sum(picked_counter.values()) / len(picked_counter) if picked_counter else 0.0
                for setup_node in worker_setup:
                    # validate ergodicity of setup picking from this node
                    self.assertLessEqual(int(abs(picked_counter[setup_node] - average_picked_counter)), 1)
                    # may not be picked by some setup that was needed for it to be setup ready
                    self.assertGreaterEqual(max(picked_counter[setup_node],
                                                picked_by_setup.get_counters(node=setup_node, worker=worker)), 1)
                    # each setup/cleanup node dropped exactly once per worker
                    self.assertEqual(dropped_setup.get_counters(node=setup_node, worker=worker), 1)
                picked_counter = {c: c._picked_by_setup_nodes.get_counters(node=node, worker=worker) for c in worker_cleanup}
                average_picked_counter = sum(picked_counter.values()) / len(picked_counter) if picked_counter else 0.0
                for cleanup_node in worker_cleanup:
                    # validate ergodicity of cleanup picking from this node
                    self.assertLessEqual(int(abs(picked_counter[cleanup_node] - average_picked_counter)), 1)
                    # picked at least once from each cleanup node (for one or all workers if flat)
                    self.assertGreaterEqual(picked_by_cleanup.get_counters(node=cleanup_node, worker=worker), 1)
                    # each cleanup node dropped exactly once per worker
                    self.assertEqual(dropped_cleanup.get_counters(node=cleanup_node, worker=worker), 1)

                # whether picked as a parent or child, a node has to be traversed at least once
                graph.traverse_node.assert_any_call(node, worker, {"dry_run": "yes"})
                self.assertGreaterEqual(len([c for c in traverse_calls if c.args[0] == node and c.args[1] == worker]), 1)
                # node should have been reversed by this worker and done so exactly once
                graph.reverse_node.assert_any_call(node, worker, {"dry_run": "yes"})
                self.assertEqual(len([r for r in reverse_calls if r == mock.call(node, worker, mock.ANY)]), 1)
                # setup should always be reversed after reversed in the right order
                for setup_node in worker_setup:
                    if setup_node.is_shared_root():
                        continue
                    self.assertGreater(reverse_calls.index(mock.call(setup_node, worker, mock.ANY)),
                                       reverse_calls.index(mock.call(node, worker, mock.ANY)))
                for cleanup_node in worker_cleanup:
                    self.assertLess(reverse_calls.index(mock.call(cleanup_node, worker, mock.ANY)),
                                    reverse_calls.index(mock.call(node, worker, mock.ANY)))

                # the shared root can be traversed many times but never reversed
                shared_roots = graph.get_nodes("shared_root", "yes")
                assert len(shared_roots) == 1, "There can be only exactly one starting node (shared root)"
                root = shared_roots[0]
                graph.traverse_node.assert_any_call(root, worker, mock.ANY)
                self.assertNotIn(mock.call(root, worker, mock.ANY), reverse_calls)

    def test_trace_work_external(self):
        """Test a multi-object test run with reusable setup of diverging workers and shared pool or previous runs."""
        graph = self._load_for_parsing("normal..tutorial1,normal..tutorial3",
                                       {"nets": " ".join([f"net{i+1}" for i in range(4)]),
                                        "shared_pool": self.config["param_dict"]["shared_pool"]})

        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["customize"][self.shared_pool] = True
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "nets": "^net1$",
             "get_location_image1_vm1": ":/mnt/local/images/shared"},
            {"shortname": "^internal.automated.connect.vm1", "vms": "^vm1$", "nets": "^net2$",
             "get_location_image1_vm1": ":/mnt/local/images/shared"},
            {"shortname": "^normal.nongui.quicktest.tutorial1.vm1", "vms": "^vm1$", "nets": "^net1$",
             "get_location_vm1": ":/mnt/local/images/shared net1:/mnt/local/images/swarm"},
            {"shortname": "^normal.nongui.tutorial3", "vms": "^vm1 vm2$", "nets": "^net2$",
             "get_location_image1_vm1": ":/mnt/local/images/shared net2:/mnt/local/images/swarm"},
        ]

        self._run_traversal(graph, self.config["param_dict"])
        # expect four sync and no other cleanup calls, one for each worker
        for action in ["get"]:
            for state in ["install", "customize"]:
                # called once by worker for for each of two vms (no self-sync as setup is from previous run or shared pool)
                # NOTE: any such use cases assume the previous setup is fully synced across all workers, if this is not the case
                # it must be due to interrupted run in which case the setup is not guaranteed to be reusable on the first place
                self.assertLessEqual(DummyStateControl.asserted_states[action][state][self.shared_pool], 2*4)
            for state in ["on_customize", "connect"]:
                # called once by worker only for vm1 (excluding self-sync as setup is provided by the swarm pool)
                self.assertLessEqual(DummyStateControl.asserted_states[action][state][self.shared_pool], 1*4-1*1)
        for action in ["set", "unset"]:
            for state in DummyStateControl.asserted_states[action]:
                self.assertEqual(DummyStateControl.asserted_states[action][state][self.shared_pool], 0)

    def test_trace_work_swarm(self):
        """Test a multi-object test run where the workers will run multiple tests reusing their own local swarm setup."""
        graph = self._load_for_parsing("leaves..tutorial2,leaves..tutorial_gui",
                                       {"nets": " ".join([f"net{i+1}" for i in range(4)]),
                                        "shared_pool": self.config["param_dict"]["shared_pool"]})

        workers = sorted(list(graph.workers.values()), key=lambda x: x.params["name"])
        self.assertEqual(len(workers), 4)
        self.assertEqual(workers[0].params["nets_spawner"], "lxc")
        self.assertEqual(workers[1].params["nets_spawner"], "lxc")
        self.assertEqual(workers[2].params["nets_spawner"], "lxc")
        self.assertEqual(workers[3].params["nets_spawner"], "lxc")
        self.assertEqual(workers[0].params["nets_shell_host"], "192.168.254.101")
        self.assertEqual(workers[1].params["nets_shell_host"], "192.168.254.102")
        self.assertEqual(workers[2].params["nets_shell_host"], "192.168.254.103")
        self.assertEqual(workers[3].params["nets_shell_host"], "192.168.254.104")
        self.assertEqual(workers[0].params["nets_shell_port"], "22")
        self.assertEqual(workers[1].params["nets_shell_port"], "22")
        self.assertEqual(workers[2].params["nets_shell_port"], "22")
        self.assertEqual(workers[3].params["nets_shell_port"], "22")

        # this is not what we test but simply a means to remove some initial nodes for simpler testing
        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["customize"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["guisetup.noop"] = {self.shared_pool: False}
        DummyStateControl.asserted_states["check"]["guisetup.clicked"] = {self.shared_pool: False}
        DummyStateControl.asserted_states["get"]["guisetup.noop"] = {self.shared_pool: 0}
        DummyStateControl.asserted_states["get"]["guisetup.clicked"] = {self.shared_pool: 0}
        DummyStateControl.asserted_states["unset"] = {"guisetup.noop": {self.shared_pool: 0}}
        DummyTestRun.asserted_tests = [
            # net1 starts from first tutorial2 variant and provides vm1 setup
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "nets": "^net1$",
             "nets_spawner": "lxc", "nets_gateway": "^$", "nets_host": "^c101$"},
            # net2 starts from second tutorial variant and steps back from its single (same) setup (net1)
            # net3 starts from first gui test and provides vm1 setup
            {"shortname": "^internal.automated.linux_virtuser.vm1", "vms": "^vm1$", "nets": "^net3$",
             "nets_spawner": "lxc", "nets_gateway": "^$", "nets_host": "^c103$"},
            # net4 starts from second gui test and provides vm2 setup
            {"shortname": "^internal.automated.windows_virtuser.vm2", "vms": "^vm2$", "nets": "^net4$",
             "nets_spawner": "lxc", "nets_gateway": "^$", "nets_host": "^c104$"},
            # net1 now moves on to its planned test
            {"shortname": "^leaves.quicktest.tutorial2.files.vm1", "vms": "^vm1$", "nets": "^net1$",
             "nets_spawner": "lxc", "nets_gateway": "^$", "nets_host": "^c101$",
             "get_location_vm1": r"[\w:/]+ net1:/mnt/local/images/swarm",
             "nets_shell_host_net1": "^192.168.254.101$", "nets_shell_port_net1": "22"},
            # net2 now steps back from tutorial2.files newly occupied by net1
            # net3 is done with half of the setup for client_noop and waits for net4 to provide the other half
            # net4 now moves on to its planned test
            {"shortname": "^leaves.tutorial_gui.client_clicked", "vms": "^vm1 vm2$", "nets": "^net4$",
             "nets_spawner": "lxc", "nets_gateway": "^$", "nets_host": "^c104$",
             "get_location_image1_vm1": r"[\w:/]+ net3:/mnt/local/images/swarm", "get_location_image1_vm2": r"[\w:/]+ net4:/mnt/local/images/swarm",
             "nets_shell_host_net3": "^192.168.254.103$", "nets_shell_host_net4": "^192.168.254.104$",
             "nets_shell_port_net3": "22", "nets_shell_port_net4": "22"},
            # net1 continues to the second tutorial2
            {"shortname": "^leaves.quicktest.tutorial2.names.vm1", "vms": "^vm1$", "nets": "^net1$",
             "nets_spawner": "lxc", "nets_gateway": "^$", "nets_host": "^c101$",
             "get_location_vm1": r"[\w:/]+ net1:/mnt/local/images/swarm",
             "nets_shell_host_net1": "^192.168.254.101$", "nets_shell_port_net1": "22"},
            # net2 picks the first gui test before net3's turn
            {"shortname": "^leaves.tutorial_gui.client_noop", "vms": "^vm1 vm2$", "nets": "^net2$",
             "nets_spawner": "lxc", "nets_gateway": "^$", "nets_host": "^c102$",
             "get_location_image1_vm1": r"[\w:/]+ net3:/mnt/local/images/swarm", "get_location_image1_vm2": r"[\w:/]+ net4:/mnt/local/images/swarm",
             "nets_shell_host_net3": "^192.168.254.103$", "nets_shell_host_net4": "^192.168.254.104$",
             "nets_shell_port_net3": "22", "nets_shell_port_net4": "22"},
        ]

        self._run_traversal(graph, self.config["param_dict"])
        # expect four sync and one cleanup calls
        self.assertEqual(DummyStateControl.asserted_states["unset"]["guisetup.noop"][self.shared_pool], 1*1)
        self.assertLessEqual(DummyStateControl.asserted_states["get"]["guisetup.clicked"][self.shared_pool], 1*4)

    def test_trace_work_remote(self):
        """Test a multi-object test run where the workers will run multiple tests reusing also remote swarm setup."""
        nets = " ".join(param.all_suffixes_by_restriction("only cluster1,cluster2\nonly net6,net7\n"))
        graph = self._load_for_parsing("leaves..tutorial2,leaves..tutorial_gui",
                                       {"nets": nets,
                                        "shared_pool": self.config["param_dict"]["shared_pool"]})

        workers = sorted(list(graph.workers.values()), key=lambda x: x.params["name"])
        self.assertEqual(len(workers), 4)
        self.assertEqual(workers[0].params["nets_spawner"], "remote")
        self.assertEqual(workers[1].params["nets_spawner"], "remote")
        self.assertEqual(workers[2].params["nets_spawner"], "remote")
        self.assertEqual(workers[3].params["nets_spawner"], "remote")
        self.assertEqual(workers[0].params["nets_shell_host"], "cluster1.net.lan")
        self.assertEqual(workers[1].params["nets_shell_host"], "cluster1.net.lan")
        self.assertEqual(workers[2].params["nets_shell_host"], "cluster2.net.lan")
        self.assertEqual(workers[3].params["nets_shell_host"], "cluster2.net.lan")
        self.assertEqual(workers[0].params["nets_shell_port"], "221")
        self.assertEqual(workers[1].params["nets_shell_port"], "222")
        self.assertEqual(workers[2].params["nets_shell_port"], "221")
        self.assertEqual(workers[3].params["nets_shell_port"], "222")

        # this is not what we test but simply a means to remove some initial nodes for simpler testing
        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["customize"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["guisetup.noop"] = {self.shared_pool: False}
        DummyStateControl.asserted_states["check"]["guisetup.clicked"] = {self.shared_pool: False}
        DummyStateControl.asserted_states["get"]["guisetup.noop"] = {self.shared_pool: 0}
        DummyStateControl.asserted_states["get"]["guisetup.clicked"] = {self.shared_pool: 0}
        DummyStateControl.asserted_states["unset"] = {"guisetup.noop": {self.shared_pool: 0}}
        DummyTestRun.asserted_tests = [
            # TODO: localhost is not acceptable when we mix hosts
            # order of the tests must be identical to the swarm work tracing
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "nets": "^cluster1.net6$",
             "nets_spawner": "remote", "nets_gateway": "^cluster1.net.lan$", "nets_host": "^1$"},
            {"shortname": "^internal.automated.linux_virtuser.vm1", "vms": "^vm1$", "nets": "^cluster2.net6$",
             "nets_spawner": "remote", "nets_gateway": "^cluster2.net.lan$", "nets_host": "^1$"},
            {"shortname": "^internal.automated.windows_virtuser.vm2", "vms": "^vm2$", "nets": "^cluster2.net7$",
             "nets_spawner": "remote", "nets_gateway": "^cluster2.net.lan$", "nets_host": "^2$"},
            {"shortname": "^leaves.quicktest.tutorial2.files.vm1", "vms": "^vm1$", "nets": "^cluster1.net6$",
             "nets_spawner": "remote", "nets_gateway": "^cluster1.net.lan$", "nets_host": "^1$",
             "get_location_vm1": r"[\w:/]+ cluster1.net6:/mnt/local/images/swarm",
             "nets_shell_host_cluster1.net6": "^cluster1.net.lan$", "nets_shell_port_cluster1.net6": "221"},
            {"shortname": "^leaves.tutorial_gui.client_clicked", "vms": "^vm1 vm2$", "nets": "^cluster2.net7$",
             "nets_spawner": "remote", "nets_gateway": "^cluster2.net.lan$", "nets_host": "^2$",
             "get_location_image1_vm1": r"[\w:/]+ cluster2.net6:/mnt/local/images/swarm", "get_location_image1_vm2": r"[\w:/]+ cluster2.net7:/mnt/local/images/swarm",
             "nets_shell_host_cluster2.net6": "^cluster2.net.lan$", "nets_shell_host_cluster2.net7": "^cluster2.net.lan$",
             "nets_shell_port_cluster2.net6": "221", "nets_shell_port_cluster2.net7": "222"},
            {"shortname": "^leaves.quicktest.tutorial2.names.vm1", "vms": "^vm1$", "nets": "^cluster1.net6$",
             "nets_spawner": "remote", "nets_gateway": "^cluster1.net.lan$", "nets_host": "^1$",
             "get_location_vm1": r"[\w:/]+ cluster1.net6:/mnt/local/images/swarm",
             "nets_shell_host_cluster1.net6": "^cluster1.net.lan$", "nets_shell_port_cluster1.net6": "221"},
            {"shortname": "^leaves.tutorial_gui.client_noop", "vms": "^vm1 vm2$", "nets": "^cluster1.net7$",
             "nets_spawner": "remote", "nets_gateway": "^cluster1.net.lan$", "nets_host": "^2$",
             "get_location_image1_vm1": r"[\w:/]+ cluster2.net6:/mnt/local/images/swarm", "get_location_image1_vm2": r"[\w:/]+ cluster2.net7:/mnt/local/images/swarm",
             "nets_shell_host_cluster2.net6": "^cluster2.net.lan$", "nets_shell_host_cluster2.net7": "^cluster2.net.lan$",
             "nets_shell_port_cluster2.net6": "221", "nets_shell_port_cluster2.net7": "222"},
        ]

        self._run_traversal(graph, self.config["param_dict"])
        # expect four sync and one cleanup calls
        self.assertEqual(DummyStateControl.asserted_states["unset"]["guisetup.noop"][self.shared_pool], 1*1)
        self.assertLessEqual(DummyStateControl.asserted_states["get"]["guisetup.clicked"][self.shared_pool], 1*4)

    def test_trace_work_preparsed(self):
        """Test a multi-object parsed in advance test run where the workers will run multiple tests reusing their setup."""
        self.config["param_dict"]["nets"] = "net1 net2 net3 net4"
        self.config["tests_str"] = "only leaves\n"
        self.config["tests_str"] += "only tutorial2,tutorial_gui\n"
        graph = TestGraph.parse_object_trees(
            None, self.config["tests_str"],
            self.prefix, self.config["vm_strs"],
            self.config["param_dict"],
        )
        # this is not what we test but simply a means to remove some initial nodes for simpler testing
        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["customize"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["guisetup.noop"] = {self.shared_pool: False}
        DummyStateControl.asserted_states["check"]["guisetup.clicked"] = {self.shared_pool: False}
        DummyStateControl.asserted_states["get"]["guisetup.noop"] = {self.shared_pool: 0}
        DummyStateControl.asserted_states["get"]["guisetup.clicked"] = {self.shared_pool: 0}
        DummyStateControl.asserted_states["unset"] = {"guisetup.noop": {self.shared_pool: 0}}
        DummyTestRun.asserted_tests = [
            {"shortname": "^internal.automated.on_customize.vm1", "vms": "^vm1$", "nets": "^net1$"},
            {"shortname": "^internal.automated.windows_virtuser.vm2", "vms": "^vm2$", "nets": "^net2$"},
            # this tests reentry of traversed path by an extra worker net4 reusing setup from net1
            {"shortname": "^internal.automated.linux_virtuser.vm1", "vms": "^vm1$", "nets": "^net3$"},
            # net4 would step back from already occupied windows_virtuser (by net2) and wander off
            {"shortname": "^leaves.quicktest.tutorial2.files.vm1", "vms": "^vm1$", "nets": "^net1$",
             "get_location_vm1": r"[\w:/]+ net1:/mnt/local/images/swarm"},
            # net2 would step back from already occupied linux_virtuser (by net3) and net3 proceeds from most distant path
            {"shortname": "^leaves.tutorial_gui.client_clicked", "vms": "^vm1 vm2$", "nets": "^net3$",
             "get_location_image1_vm1": r"[\w:/]+ net3:/mnt/local/images/swarm", "get_location_image1_vm2": r"[\w:/]+ net2:/mnt/local/images/swarm"},
            # net4 now picks up available setup and tests after wandering off from occupied node
            {"shortname": "^leaves.quicktest.tutorial2.names.vm1", "vms": "^vm1$", "nets": "^net4$",
             "get_location_vm1": r"[\w:/]+ net1:/mnt/local/images/swarm"},
            # net1 would bounce off the already occupied tutorial2.names
            {"shortname": "^leaves.tutorial_gui.client_noop", "vms": "^vm1 vm2$", "nets": "^net2$",
             "get_location_image1_vm1": r"[\w:/]+ net3:/mnt/local/images/swarm", "get_location_image1_vm2": r"[\w:/]+ net2:/mnt/local/images/swarm"},
            # all others now step back from already occupied tutorial2.names (by net1)
        ]
        self._run_traversal(graph, self.config["param_dict"])
        # expect four sync and one cleanup calls
        self.assertEqual(DummyStateControl.asserted_states["unset"]["guisetup.noop"][self.shared_pool], 1)
        self.assertEqual(DummyStateControl.asserted_states["get"]["guisetup.clicked"][self.shared_pool], 4)

        self._run_traversal(graph, self.config["param_dict"])
        # expect four sync and one cleanup calls
        self.assertEqual(DummyStateControl.asserted_states["unset"]["guisetup.noop"][self.shared_pool], 1)
        self.assertEqual(DummyStateControl.asserted_states["get"]["guisetup.clicked"][self.shared_pool], 4)

    def test_cloning_simple_permanent_object(self):
        """Test a complete test run including complex setup that involves permanent vms and cloning."""
        graph = self._load_for_parsing("leaves..tutorial_get", {"nets": "net1"})

        DummyStateControl.asserted_states["check"]["root"] = {self.shared_pool: True}
        DummyStateControl.asserted_states["check"].update({"guisetup.noop": {self.shared_pool: False}, "guisetup.clicked": {self.shared_pool: False},
                                                           "getsetup.noop": {self.shared_pool: False}, "getsetup.clicked": {self.shared_pool: False},
                                                           "getsetup.guisetup.noop": {self.shared_pool: False},
                                                           "getsetup.guisetup.clicked": {self.shared_pool: False}})
        # test syncing also for permanent vms
        DummyStateControl.asserted_states["get"]["ready"] = {self.shared_pool: 0}
        # TODO: currently not used due to excluded self-sync but one that is not the correct implementation
        DummyStateControl.asserted_states["get"].update({"guisetup.noop": {self.shared_pool: 0}, "guisetup.clicked": {self.shared_pool: 0},
                                                         "getsetup.noop": {self.shared_pool: 0}, "getsetup.clicked": {self.shared_pool: 0},
                                                         "getsetup.guisetup.noop": {self.shared_pool: 0},
                                                         "getsetup.guisetup.clicked": {self.shared_pool: 0}})
        DummyStateControl.asserted_states["unset"] = {"guisetup.noop": {self.shared_pool: 0},
                                                      "getsetup.noop": {self.shared_pool: 0},
                                                      "ready": {self.shared_pool: 0}}
        DummyTestRun.asserted_tests = [
            # automated setup of vm1 from tutorial_gui
            {"shortname": "^internal.stateless.noop.vm1", "vms": "^vm1$"},
            {"shortname": "^original.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads.vm1", "vms": "^vm1$"},
            {"shortname": "^internal.automated.customize.vm1", "vms": "^vm1$"},
            # automated setup of vm1 from tutorial_get
            {"shortname": "^internal.automated.connect.vm1", "vms": "^vm1$"},
            # vm2 image of explicit_noop that the worker started from depends on tutorial_gui which needs another state of vm1
            {"shortname": "^internal.automated.linux_virtuser.vm1", "vms": "^vm1$"},
            # automated setup of vm2 from tutorial_gui
            {"shortname": "^internal.stateless.noop.vm2", "vms": "^vm2$"},
            {"shortname": "^original.unattended_install.cdrom.extra_cdrom_ks.default_install.aio_threads.vm2", "vms": "^vm2$"},
            {"shortname": "^internal.automated.customize.vm2", "vms": "^vm2$"},
            {"shortname": "^internal.automated.windows_virtuser.vm2", "vms": "^vm2$"},
            # first (noop) parent GUI setup dependency through vm2
            {"shortname": "^tutorial_gui.client_noop.vm1.+CentOS.8.0.+vm2.+Win10", "vms": "^vm1 vm2$", "set_state_images_vm2": "guisetup.noop"},
            # first (noop) explicit actual test
            {"shortname": "^leaves.tutorial_get.explicit_noop.vm1", "vms": "^vm1 vm2 vm3$", "get_state_images_vm2": "guisetup.noop"},
            # second (clicked) parent GUI setup dependency through vm2
            {"shortname": "^tutorial_gui.client_clicked.vm1", "vms": "^vm1 vm2$", "set_state_images_vm2": "guisetup.clicked"},
            # second (clicked) explicit actual test
            {"shortname": "^leaves.tutorial_get.explicit_clicked.vm1", "vms": "^vm1 vm2 vm3$", "get_state_images_vm2": "guisetup.clicked"},
            # first (noop) duplicated actual test (child priority to reuse setup)
            {"shortname": "^leaves.tutorial_get.implicit_both.guisetup.noop.vm1", "vms": "^vm1 vm2 vm3$", "get_state_images_image1_vm2": "guisetup.noop"},
            # second (clicked) duplicated actual test
            {"shortname": "^leaves.tutorial_get.implicit_both.guisetup.clicked.vm1", "vms": "^vm1 vm2 vm3$", "get_state_images_image1_vm2": "guisetup.clicked"},
        ]

        self._run_traversal(graph, self.config["param_dict"])
        # expect a single cleanup call only for the states of enforcing cleanup policy
        # expect four sync and respectively cleanup calls, one for each worker
        self.assertEqual(DummyStateControl.asserted_states["unset"]["guisetup.noop"][self.shared_pool], 1)
        self.assertEqual(DummyStateControl.asserted_states["unset"]["getsetup.noop"][self.shared_pool], 1)
        self.assertEqual(DummyStateControl.asserted_states["unset"]["ready"][self.shared_pool], 0)
        # root state of a permanent vm is not synced even once
        self.assertEqual(DummyStateControl.asserted_states["get"]["ready"][self.shared_pool], 0)

    def test_cloning_simple_cross_object(self):
        """Test a complete test run with multi-variant objects where cloning should not be affected."""
        self.job.config["vm_strs"] = {"vm1": "", "vm2": "", "vm3": "only Ubuntu\n"}
        graph = self._load_for_parsing("leaves..tutorial_get,leaves..tutorial_gui", {"nets": "net1"})

        DummyStateControl.asserted_states["check"]["root"] = {self.shared_pool: True}
        DummyStateControl.asserted_states["check"].update({"guisetup.noop": {self.shared_pool: False}, "fedora.noop": {self.shared_pool: False}, "guisetup.clicked": {self.shared_pool: False},
                                                           "getsetup.noop": {self.shared_pool: False}, "getsetup.clicked": {self.shared_pool: False},
                                                           "getsetup.guisetup.noop": {self.shared_pool: False},
                                                           "getsetup.guisetup.clicked": {self.shared_pool: False}})
        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["customize"][self.shared_pool] = True
        # test syncing also for permanent vms
        DummyStateControl.asserted_states["get"]["ready"] = {self.shared_pool: 0}
        # TODO: currently not used due to excluded self-sync but one that is not the correct implementation
        DummyStateControl.asserted_states["get"].update({"guisetup.noop": {self.shared_pool: 0}, "guisetup.clicked": {self.shared_pool: 0},
                                                         "getsetup.noop": {self.shared_pool: 0}, "getsetup.clicked": {self.shared_pool: 0},
                                                         "getsetup.guisetup.noop": {self.shared_pool: 0},
                                                         "getsetup.guisetup.clicked": {self.shared_pool: 0}})
        DummyStateControl.asserted_states["unset"] = {"guisetup.noop": {self.shared_pool: 0}, "fedora.noop": {self.shared_pool: 0},
                                                      "getsetup.noop": {self.shared_pool: 0},
                                                      "ready": {self.shared_pool: 0}}
        DummyTestRun.asserted_tests = [
            # automated setup of vm1 of CentOS variant
            {"shortname": "^internal.automated.linux_virtuser.vm1.+CentOS", "vms": "^vm1$"},
            # automated setup of vm2 of Win10 variant
            {"shortname": "^internal.automated.windows_virtuser.vm2.+Win10", "vms": "^vm2$"},
            # first (noop) parent GUI setup dependency through vm2 of Win10 variant
            {"shortname": "^leaves.tutorial_gui.client_noop.vm1.+CentOS.+vm2.+Win10", "vms": "^vm1 vm2$", "set_state_images_vm2": "guisetup.noop"},
            # second (clicked) parent GUI setup dependency through vm2 of Win10 variant
            {"shortname": "^leaves.tutorial_gui.client_clicked.vm1.+CentOS.+vm2.+Win10", "vms": "^vm1 vm2$", "set_state_images_vm2": "guisetup.clicked"},

            # automated setup of vm1 of CentOS variant from tutorial_get
            {"shortname": "^internal.automated.connect.vm1.+CentOS", "vms": "^vm1$"},
            # first (noop) explicit actual test of CentOS+Win10
            {"shortname": "^leaves.tutorial_get.explicit_noop.vm1.+CentOS.+vm2.+Win10", "vms": "^vm1 vm2 vm3$", "get_state_images_vm2": "guisetup.noop"},
            # second (clicked) explicit actual test of CentOS+Win10
            {"shortname": "^leaves.tutorial_get.explicit_clicked.vm1.+CentOS.+vm2.+Win10", "vms": "^vm1 vm2 vm3$", "get_state_images_vm2": "guisetup.clicked"},
            # first (noop) duplicated actual test of CentOS+Win10
            {"shortname": "^leaves.tutorial_get.implicit_both.guisetup.noop.vm1.+CentOS.+vm2.+Win10", "vms": "^vm1 vm2 vm3$", "get_state_images_image1_vm2": "guisetup.noop"},

            # TODO: prefix order would change the vm variants on implicit_both flat node

            # automated setup of vm2 of Win7 variant
            {"shortname": "^internal.automated.windows_virtuser.vm2.+Win7", "vms": "^vm2$"},
            # first (noop) parent GUI setup dependency through vm2 of Win7 variant
            {"shortname": "^leaves.tutorial_gui.client_noop.vm1.+CentOS.+vm2.+Win7", "vms": "^vm1 vm2$", "set_state_images_vm2": "guisetup.noop"},
            # first (noop) duplicated actual test of CentOS+Win7
            {"shortname": "^leaves.tutorial_get.implicit_both.guisetup.noop.vm1.+CentOS.+vm2.+Win7", "vms": "^vm1 vm2 vm3$", "get_state_images_image1_vm2": "guisetup.noop"},
            # second (clicked) parent GUI setup dependency through vm2 of Win7 variant
            {"shortname": "^leaves.tutorial_gui.client_clicked.vm1.+CentOS.+vm2.+Win7", "vms": "^vm1 vm2$", "set_state_images_vm2": "guisetup.clicked"},
            # second (clicked) duplicated actual test of CentOS+Win7
            {"shortname": "^leaves.tutorial_get.implicit_both.guisetup.clicked.vm1.+CentOS.+vm2.+Win7", "vms": "^vm1 vm2 vm3$", "get_state_images_image1_vm2": "guisetup.clicked"},

            # TODO: prefix order would change the vm variants on implicit_both flat node

            # second (clicked) duplicated actual test of CentOS+Win10
            {"shortname": "^leaves.tutorial_get.implicit_both.guisetup.clicked.vm1.+CentOS.+vm2.+Win10", "vms": "^vm1 vm2 vm3$", "get_state_images_image1_vm2": "guisetup.clicked"},
            # first (noop) explicit actual test of CentOS+Win7
            {"shortname": "^leaves.tutorial_get.explicit_noop..+CentOS.+vm2.+Win7", "vms": "^vm1 vm2 vm3$", "get_state_images_vm2": "guisetup.noop"},

            # automated setup of vm1 of Fedora variant, required via extra "tutorial_gui" restriction
            {"shortname": "^internal.automated.linux_virtuser.vm1.+Fedora", "vms": "^vm1$"},
            # GUI test for vm1 of Fedora variant which is not first (noop) dependency through vm2 of Win10 variant (produced with vm1 of CentOS variant)
            {"shortname": "^leaves.tutorial_gui.client_noop.vm1.+Fedora.+vm2.+Win10", "vms": "^vm1 vm2$", "set_state_images_vm2": "fedora.noop"},
            # GUI test for vm1 of Fedora variant which is not first (noop) dependency through vm2 of Win7 variant (produced with vm1 of CentOS variant)
            {"shortname": "^leaves.tutorial_gui.client_noop.vm1.+Fedora.+vm2.+Win7", "vms": "^vm1 vm2$", "set_state_images_vm2": "fedora.noop"},

            # second (clicked) explicit actual test of CentOS+Win7
            {"shortname": "^leaves.tutorial_get.explicit_clicked.vm1.+CentOS.+vm2.+Win7", "vms": "^vm1 vm2 vm3$", "get_state_images_vm2": "guisetup.clicked"},

            # GUI test for vm1 of Fedora variant which is not second (clicked) dependency through vm2 of Win10 variant (produced with vm1 of CentOS variant)
            {"shortname": "^leaves.tutorial_gui.client_clicked.vm1.+Fedora.+vm2.+Win10", "vms": "^vm1 vm2$"},
            # GUI test for vm1 of Fedora variant which is not second (clicked) dependency through vm2 of Win7 variant (produced with vm1 of CentOS variant)
            {"shortname": "^leaves.tutorial_gui.client_clicked.vm1.+Fedora.+vm2.+Win7", "vms": "^vm1 vm2$"},
        ]

        self._run_traversal(graph, self.config["param_dict"])
        # expect two cleanups of two out of four different variant product states
        self.assertEqual(DummyStateControl.asserted_states["unset"]["guisetup.noop"][self.shared_pool], 2)
        # expect two cleanups of two different variant product states (vm1 variant restricted)
        self.assertEqual(DummyStateControl.asserted_states["unset"]["getsetup.noop"][self.shared_pool], 2)

    def test_cloning_deep(self):
        """Test for correct deep cloning."""
        graph = self._load_for_parsing("leaves..tutorial_finale", {"nets": "net1"})

        DummyStateControl.asserted_states["check"]["install"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"]["customize"][self.shared_pool] = True
        DummyStateControl.asserted_states["check"].update({"guisetup.noop": {self.shared_pool: False}, "guisetup.clicked": {self.shared_pool: False},
                                                           "getsetup.guisetup.noop": {self.shared_pool: False},
                                                           "getsetup.guisetup.clicked": {self.shared_pool: False}})
        # TODO: currently not used due to excluded self-sync but one that is not the correct implementation
        DummyStateControl.asserted_states["get"].update({"guisetup.noop": {self.shared_pool: 0}, "guisetup.clicked": {self.shared_pool: 0},
                                                         "getsetup.guisetup.noop": {self.shared_pool: 0},
                                                         "getsetup.guisetup.clicked": {self.shared_pool: 0}})
        DummyStateControl.asserted_states["unset"] = {"guisetup.noop": {self.shared_pool: 0}, "getsetup.noop": {self.shared_pool: 0}}
        DummyTestRun.asserted_tests = [
            # extra dependency dependency through vm1
            {"shortname": "^internal.automated.connect.vm1", "vms": "^vm1$"},
            # automated setup of vm1
            {"shortname": "^internal.automated.linux_virtuser.vm1", "vms": "^vm1$"},
            # automated setup of vm2
            {"shortname": "^internal.automated.windows_virtuser.vm2", "vms": "^vm2$"},
            # first (noop) parent GUI setup dependency through vm2
            {"shortname": "^tutorial_gui.client_noop", "vms": "^vm1 vm2$", "set_state_images_vm2": "guisetup.noop"},
            # first (noop) duplicated actual test
            {"shortname": "^tutorial_get.implicit_both.guisetup.noop", "vms": "^vm1 vm2 vm3$", "get_state_images_image1_vm2": "guisetup.noop", "set_state_images_image1_vm2": "getsetup.guisetup.noop"},
            {"shortname": "^leaves.tutorial_finale.getsetup.guisetup.noop", "vms": "^vm1 vm2 vm3$", "get_state_images_image1_vm2": "getsetup.guisetup.noop"},
            # second (clicked) parent GUI setup dependency through vm2
            {"shortname": "^tutorial_gui.client_clicked", "vms": "^vm1 vm2$", "set_state_images_vm2": "guisetup.clicked"},
            # second (clicked) duplicated actual test
            {"shortname": "^tutorial_get.implicit_both.guisetup.clicked", "vms": "^vm1 vm2 vm3$", "get_state_images_image1_vm2": "guisetup.clicked", "set_state_images_image1_vm2": "getsetup.guisetup.clicked"},
            {"shortname": "^leaves.tutorial_finale.getsetup.guisetup.clicked", "vms": "^vm1 vm2 vm3$", "get_state_images_image1_vm2": "getsetup.guisetup.clicked"},
        ]

        self._run_traversal(graph, self.config["param_dict"])
        # expect a single cleanup call only for the states of enforcing cleanup policy
        self.assertEqual(DummyStateControl.asserted_states["unset"]["guisetup.noop"][self.shared_pool], 1)

    @mock.patch('avocado_vt.plugins.runner.StatusRepo')
    @mock.patch('avocado_vt.plugins.runner.StatusServer')
    @mock.patch('avocado_vt.plugins.runner.TestGraph')
    @mock.patch('avocado_vt.plugins.loader.TestGraph')
    def test_loader_runner_entries(self, mock_load_graph, mock_run_graph,
                                   mock_status_server, _mock_status_repo):
        """Test that the default loader and runner entries work as expected."""
        self.config["tests_str"] += "only tutorial1\n"
        reference = "only=tutorial1 key1=val1"
        self.config["params"] = reference.split()
        self.config["prefix"] = ""
        self.config["subcommand"] = "run"

        mock_load_graph.parse_flat_nodes.return_value = [TestNode(prefix="1", recipe=None),
                                                         TestNode(prefix="2", recipe=None)]

        self.loader.config = self.config
        resolutions = [self.loader.resolve(reference)]
        mock_load_graph.parse_flat_nodes.assert_called_with(self.config["tests_str"],
                                                            self.config["param_dict"])
        runnables = resolutions_to_runnables(resolutions, self.config)
        test_suite = TestSuite('suite',
                               config=self.config,
                               tests=runnables,
                               resolutions=resolutions)
        self.assertEqual(len(test_suite), 2)

        # test status result collection needs a lot of extra mocking as a boundary
        async def create_server(): pass
        async def serve_forever(): pass
        server_instance = mock_status_server.return_value
        server_instance.create_server = create_server
        server_instance.serve_forever = serve_forever
        self.runner._update_status = mock.AsyncMock()

        run_graph_instance = mock_run_graph.return_value
        run_graph_instance.restrs = {}
        run_graph_instance.traverse_object_trees = mock.AsyncMock()
        run_graph_workers = run_graph_instance.workers.values.return_value = [mock.MagicMock()]
        run_graph_workers[0].params = {"name": "net1"}

        self.runner.job.config = self.config
        self.runner.run_suite(self.runner.job, test_suite)
        self.assertEqual(run_graph_instance.restrs, self.runner.job.config["vm_strs"])
        run_graph_instance.parse_shared_root_from_object_roots.assert_called_once()
        mock_run_graph.parse_workers.assert_called_once()
        run_graph_workers[0].start.assert_called()
        run_graph_instance.traverse_object_trees.assert_called()


if __name__ == '__main__':
    unittest.main()
