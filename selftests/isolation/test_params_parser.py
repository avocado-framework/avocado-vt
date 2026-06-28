#!/usr/bin/env python

import unittest
import unittest_importer

from avocado import Test
from virttest.utils_params import Params

import avocado_i2n.params_parser as param


class ParamsParserTest(Test):

    def setUp(self):
        self.base_dict = {}
        self.base_str = "only normal\n"
        self.base_file = "sets.cfg"
        self.show_restriction = False
        self.show_dictionaries = False
        self.show_dict_fullname = False
        self.show_dict_contents = False

    def tearDown(self):
        pass

    def test_all_suffixes_by_restriction(self):
        """Test a resulting list of suffixes from a suffix variant restriction."""
        output = param.all_suffixes_by_restriction("only cluster1", key="nets")
        self.assertEqual(output, ["cluster1.net6", "cluster1.net7",
                                  "cluster1.net8", "cluster1.net9"])

        output = param.all_suffixes_by_restriction("no localhost, net6, net7", key="nets")
        self.assertEqual(output, ["cluster1.net8", "cluster1.net9",
                                  "cluster2.net8", "cluster2.net9"])

    def test_join_str(self):
        """Test a resulting join string satifies certain syntactic form."""
        output = param.join_str({"vm2": "param1 = A\n", "vm1": "only a"},
                                 "vms", base_str="param2 = B\n")
        self.assertEqual(output, "param2 = B\n"
                                 "vm1:\n"
                                 "    only a\n"
                                 "vm2:\n"
                                 "    param1 = A\n"
                                 "join vm1 vm2\n")

        with self.assertRaises(ValueError):
            param.join_str({"vm_VARIANT_NOT_IN_VMS": "param1 = A\n"},
                            "vms")

    def test_parser_params(self):
        """Test that parameters obtain from parser or directly are the same."""
        self.base_str += "only tutorial1\n"
        config = param.Reparsable()
        config.parse_next_batch(base_file=self.base_file,
                                base_str=self.base_str,
                                base_dict=self.base_dict)
        parser = config.get_parser(show_restriction=False,
                                   show_dictionaries=False,
                                   show_dict_fullname=False,
                                   show_dict_contents=False)
        params = config.get_params(show_restriction=False,
                                   show_dictionaries=False,
                                   show_dict_fullname=False,
                                   show_dict_contents=False)
        d = parser.get_dicts().__next__()
        for key in params.keys():
            self.assertEqual(params[key], d[key], "The %s parameter must coincide: %s != %s" % (key, params[key], d[key]))

    def test_params_dict_index(self):
        """Test that parameters obtained via an additional dictionary index are the correct ones."""
        self.base_str = "only all..tutorial2\n"
        config = param.Reparsable()
        config.parse_next_batch(base_file=self.base_file,
                                base_str=self.base_str,
                                base_dict=self.base_dict)
        parser = config.get_parser(show_restriction=False,
                                   show_dictionaries=False,
                                   show_dict_fullname=False,
                                   show_dict_contents=False)
        params = config.get_params(dict_index=1,
                                   show_restriction=False,
                                   show_dictionaries=False,
                                   show_dict_fullname=False,
                                   show_dict_contents=False)
        for i, d in enumerate(parser.get_dicts()):
            if i == 1:
                for key in params.keys():
                    self.assertEqual(params[key], d[key], "The %s parameter must coincide: %s != %s" % (key, params[key], d[key]))

        with self.assertRaises(ValueError):
            config.get_params(dict_index=2)


if __name__ == '__main__':
    unittest.main()
