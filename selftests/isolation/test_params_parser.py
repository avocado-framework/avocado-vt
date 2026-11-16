#!/usr/bin/env python

import unittest
from unittest import mock

from avocado import Test

import virttest.params_parser as param
from virttest.cartconf import IS_VARIANTER, Parser
from virttest.cartesian_config import Parser as LegacyParser


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
        self.assertEqual(
            output, ["cluster1.net6", "cluster1.net7", "cluster1.net8", "cluster1.net9"]
        )

        output = param.all_suffixes_by_restriction(
            "no localhost, net6, net7", key="nets"
        )
        self.assertEqual(
            output, ["cluster1.net8", "cluster1.net9", "cluster2.net8", "cluster2.net9"]
        )

    def test_join_str(self):
        """Test that a resulting join string satisfies a certain syntactic form."""
        output = param.join_str(
            {"vm2": "param1 = A\n", "vm1": "only a"}, "vms", base_str="param2 = B\n"
        )
        self.assertEqual(
            output,
            "param2 = B\n"
            "vm1:\n"
            "    only a\n"
            "vm2:\n"
            "    param1 = A\n"
            "join vm1 vm2\n",
        )

        with self.assertRaises(ValueError):
            param.join_str({"vm_VARIANT_NOT_IN_VMS": "param1 = A\n"}, "vms")

    @unittest.skipUnless(IS_VARIANTER, "Parser caching requires CartConf")
    @mock.patch.dict(param.Reparsable._parse_cache, clear=True)
    @mock.patch.object(Parser, "parse_string", wraps=Parser.parse_string, autospec=True)
    @mock.patch.object(Parser, "parse_file", wraps=Parser.parse_file, autospec=True)
    def test_get_parser_cached(self, mock_parse_file, mock_parse_string):
        """Test that a parser is cached and retrieved correctly."""
        self.base_dict = {"key1": "value1"}
        config = param.Reparsable()
        config.parse_next_batch(
            base_file=self.base_file,
            base_str=self.base_str,
            base_dict=self.base_dict,
        )
        parser = config.get_parser(
            show_restriction=False,
            show_dictionaries=False,
            show_dict_fullname=False,
            show_dict_contents=False,
        )
        self.assertEqual(
            mock_parse_file.call_count,
            1,
            "parse_file should be called on first invocation",
        )
        self.assertEqual(
            mock_parse_string.call_count,
            5,
            "parse_string should be called on first invocation",
        )
        self.assertEqual(
            len(config._parse_cache),
            1,
            "cache should have one entry which is for the file",
        )
        file_key = config.steps[0].parsable_form()
        self.assertEqual(mock_parse_file.mock_calls[0].args[1], file_key.split()[1])
        self.assertIn(file_key, config._parse_cache)
        self.assertIsNotNone(
            config._parse_cache[file_key]["parser"],
            "cached parser must be stored for the file parsing step",
        )
        self.assertEqual(
            len(config._parse_cache[file_key]["children"]),
            1,
            "subcache should have one entry which is for the string",
        )
        str_key = "only normal\n"
        self.assertEqual(mock_parse_string.mock_calls[3].args[1], str_key)
        self.assertIn(str_key, config._parse_cache[file_key]["children"])
        self.assertIsNotNone(
            config._parse_cache[file_key]["children"][str_key]["parser"],
            "cached parser must be stored for the string parsing step",
        )
        self.assertEqual(
            len(config._parse_cache[file_key]["children"][str_key]["children"]),
            1,
            "subcache should have one entry which is for the dictionary",
        )
        dict_key = "key1 = value1\n"
        self.assertEqual(mock_parse_string.mock_calls[4].args[1], dict_key)
        self.assertIn(
            dict_key,
            config._parse_cache[file_key]["children"][str_key]["children"],
        )
        self.assertIsNotNone(
            config._parse_cache[file_key]["children"][str_key]["children"][dict_key][
                "parser"
            ],
            "cached parser must be stored for the dictionary parsing step",
        )
        self.assertEqual(
            len(
                config._parse_cache[file_key]["children"][str_key]["children"][
                    dict_key
                ]["children"]
            ),
            0,
            "no subcache available for any further steps",
        )

        # second call should reuse cached parser without calling parse_string or parse_file
        parser2 = config.get_parser(
            show_restriction=False,
            show_dictionaries=False,
            show_dict_fullname=False,
            show_dict_contents=False,
        )
        self.assertEqual(
            mock_parse_string.call_count,
            5,
            "parse_string should not be called again on second invocation",
        )
        self.assertEqual(
            mock_parse_file.call_count,
            1,
            "parse_file should not be called again on second invocation",
        )
        self.assertEqual(
            list(parser.get_dicts()),
            list(parser2.get_dicts()),
            "cached parser should produce the same dictionaries",
        )

        # different Reparsable with same steps reuses the cache
        config2 = param.Reparsable()
        config2.parse_next_batch(
            base_file=self.base_file,
            base_str=self.base_str,
            base_dict=self.base_dict,
        )
        # third call from a different Reparsable should also reuse cache
        parser3 = config2.get_parser(
            show_restriction=False,
            show_dictionaries=False,
            show_dict_fullname=False,
            show_dict_contents=False,
        )
        # verify that parsing methods were NOT called for this second Reparsable
        # since it has the same steps that were already cached
        self.assertEqual(
            mock_parse_string.call_count,
            5,
            "parse_string should not be called when all steps are cached",
        )
        self.assertEqual(
            mock_parse_file.call_count,
            1,
            "parse_file should not be called when all steps are cached",
        )
        self.assertEqual(
            list(parser.get_dicts()),
            list(parser3.get_dicts()),
            "cached parser should be reused for different Reparsable instances",
        )
        initial_str_calls = list(mock_parse_string.mock_calls)
        initial_file_calls = list(mock_parse_file.mock_calls)

        # different Reparsable with same initial steps reuses the cache for these steps
        config3 = param.Reparsable()
        config3.parse_next_batch(
            base_file=self.base_file,
            base_str=self.base_str,
            base_dict={"key2": "value2"},
        )
        # fourth call with different base_dict should reuse 2-stage cache and not 3-stage
        parser4 = config3.get_parser(
            show_restriction=False,
            show_dictionaries=False,
            show_dict_fullname=False,
            show_dict_contents=False,
        )
        # verify that parsing methods were called for specific stages
        self.assertEqual(
            mock_parse_string.call_count,
            6,
            "parse_string should be called for the new dict",
        )
        self.assertEqual(
            mock_parse_file.call_count,
            1,
            "parse_file should not be called when all steps are cached",
        )
        self.assertEqual(mock_parse_file.mock_calls, initial_file_calls)
        dict_key2 = "key2 = value2\n"
        self.assertEqual(mock_parse_string.mock_calls[5].args[1], dict_key2)
        self.assertEqual(
            len(config._parse_cache),
            1,
            "cache should have one entry which is for the file",
        )
        self.assertEqual(
            len(config._parse_cache[file_key]["children"]),
            1,
            "subcache should have one entry which is for the string",
        )
        self.assertEqual(
            len(config._parse_cache[file_key]["children"][str_key]["children"]),
            2,
            "subcache should now have two entries which are for the branched dictionaries",
        )
        self.assertEqual(
            len(
                config._parse_cache[file_key]["children"][str_key]["children"][
                    dict_key
                ]["children"]
            ),
            0,
            "no subcache available for any further steps",
        )
        self.assertIn(
            dict_key,
            config._parse_cache[file_key]["children"][str_key]["children"],
        )
        self.assertIsNotNone(
            config._parse_cache[file_key]["children"][str_key]["children"][dict_key2][
                "parser"
            ],
            "cached parser must be stored for the dictionary parsing step",
        )
        self.assertEqual(
            len(
                config._parse_cache[file_key]["children"][str_key]["children"][
                    dict_key2
                ]["children"]
            ),
            0,
            "no subcache available for any further steps",
        )

        self.assertGreater(len(list(parser.get_dicts())), 0)
        dict1 = list(parser.get_dicts())[-1]
        self.assertGreater(len(list(parser4.get_dicts())), 0)
        dict4 = list(parser4.get_dicts())[-1]
        self.assertIn("key1", dict1)
        self.assertEqual(dict1["key1"], "value1")
        self.assertNotIn("key1", dict4)
        self.assertNotIn("key2", dict1)
        self.assertIn("key2", dict4)
        self.assertEqual(dict4["key2"], "value2")

    @unittest.skipUnless(IS_VARIANTER, "Parser caching requires CartConf")
    @mock.patch.dict(param.Reparsable._parse_cache, clear=True)
    def test_cached_parser_isolation(self):
        """Cached siblings share immutable syntax and remain independent."""
        base = "variants:\n    - a:\n    - b:\n"
        left = param.Reparsable()
        left.parse_next_batch(base_str=base, base_dict={"left": "1"})
        child = left.get_parser()
        expected = list(child.get_dicts())
        self.assertEqual(len(expected), 2)

        right = param.Reparsable()
        right.parse_next_batch(base_str=base, base_dict={"right": "2"})
        sibling = right.get_parser()
        # the sibling dictionaries are fully parametrically decoupled
        self.assertTrue(all("left" not in d for d in sibling.get_dicts()))
        # child dictionaries are still the same too (decoupled from sibling)
        self.assertEqual(list(child.get_dicts()), expected)

        cached = left.get_parser()
        child.parse_string("only a\n")
        self.assertEqual(len(list(child.get_dicts())), 1)
        # cached dictionaries are same despite extended child
        self.assertEqual(list(cached.get_dicts()), expected)
        # freshly reused cache has the same expected dictionaries
        self.assertEqual(list(left.get_parser().get_dicts()), expected)

    @mock.patch.object(param, "IS_VARIANTER", False)
    @mock.patch.object(param, "Parser", LegacyParser)
    @mock.patch.dict(param.Reparsable._parse_cache, clear=True)
    def test_local_parser_without_cache(self):
        """The local parser reparses requests without reading or writing the cache."""
        config = param.Reparsable()
        config.parse_next_str("variants:\n    - a:\n    - b:\n")
        config.parse_next_dict({"value": "one"})
        key = config.steps[0].parsable_form()
        cached_entry = {"parser": object(), "children": {}}
        param.Reparsable._parse_cache[key] = cached_entry
        with mock.patch.object(param, "copy") as parser_copy:
            first = config.get_parser(show_empty_cartesian_product=False)
            expected = list(first.get_dicts())
            self.assertEqual(len(expected), 2)
            first.parse_string("only a\n")
            self.assertEqual(len(list(first.get_dicts())), 1)
            second = config.get_parser(show_empty_cartesian_product=False)
            self.assertIsInstance(second, LegacyParser)
            self.assertIsNot(first, second)
            self.assertEqual(list(second.get_dicts()), expected)
            parser_copy.copy.assert_not_called()
            parser_copy.deepcopy.assert_not_called()
        self.assertEqual(param.Reparsable._parse_cache, {key: cached_entry})

    def test_parser_params(self):
        """Test that parameters obtain from parser or directly are the same."""
        self.base_str += "only tutorial1\n"
        config = param.Reparsable()
        config.parse_next_batch(
            base_file=self.base_file, base_str=self.base_str, base_dict=self.base_dict
        )
        parser = config.get_parser(
            show_restriction=False,
            show_dictionaries=False,
            show_dict_fullname=False,
            show_dict_contents=False,
        )
        params = config.get_params(
            show_restriction=False,
            show_dictionaries=False,
            show_dict_fullname=False,
            show_dict_contents=False,
        )
        d = parser.get_dicts().__next__()
        for key in params.keys():
            self.assertEqual(
                params[key],
                d[key],
                "The %s parameter must coincide: %s != %s" % (key, params[key], d[key]),
            )

    def test_params_dict_index(self):
        """Test that parameters obtained via an additional dictionary index are the correct ones."""
        self.base_str = "only all..tutorial2\n"
        config = param.Reparsable()
        config.parse_next_batch(
            base_file=self.base_file, base_str=self.base_str, base_dict=self.base_dict
        )
        parser = config.get_parser(
            show_restriction=False,
            show_dictionaries=False,
            show_dict_fullname=False,
            show_dict_contents=False,
        )
        params = config.get_params(
            dict_index=1,
            show_restriction=False,
            show_dictionaries=False,
            show_dict_fullname=False,
            show_dict_contents=False,
        )
        for i, d in enumerate(parser.get_dicts()):
            if i == 1:
                for key in params.keys():
                    self.assertEqual(
                        params[key],
                        d[key],
                        "The %s parameter must coincide: %s != %s"
                        % (key, params[key], d[key]),
                    )

        with self.assertRaises(ValueError):
            config.get_params(dict_index=2)


if __name__ == "__main__":
    unittest.main()
