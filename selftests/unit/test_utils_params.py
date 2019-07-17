#!/usr/bin/python

import unittest
import os
import sys
from collections import OrderedDict

# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(basedir, 'virttest')):
    sys.path.append(basedir)

from virttest import utils_params

BASE_DICT = {
    'image_boot': 'yes',
    'image_boot_stg': 'no',
    'image_chain': '',
    'image_clone_command': 'cp --reflink=auto %s %s',
    'image_format': 'qcow2',
    'image_format_stg': 'qcow2',
    'image_name': 'images/f18-64',
    'image_name_stg': 'enospc',
    'image_raw_device': 'no',
    'image_remove_command': 'rm -rf %s',
    'image_size': '10G',
    'image_snapshot_stg': 'no',
    'image_unbootable_pattern': 'Hard Disk.*not a bootable disk',
    'image_verify_bootable': 'yes',
    'images': 'image1 stg',
}

CORRECT_RESULT_MAPPING = {"image1": {'image_boot_stg': 'no',
                                     'image_snapshot_stg': 'no',
                                     'image_chain': '',
                                     'image_unbootable_pattern': 'Hard Disk.*not a bootable disk',
                                     'image_name': 'images/f18-64',
                                     'image_remove_command': 'rm -rf %s',
                                     'image_name_stg': 'enospc',
                                     'image_clone_command': 'cp --reflink=auto %s %s',
                                     'image_size': '10G', 'images': 'image1 stg',
                                     'image_raw_device': 'no',
                                     'image_format': 'qcow2',
                                     'image_boot': 'yes',
                                     'image_verify_bootable': 'yes',
                                     'image_format_stg': 'qcow2'},
                          "stg": {'image_snapshot': 'no',
                                  'image_boot_stg': 'no',
                                  'image_snapshot_stg': 'no',
                                  'image_chain': '',
                                  'image_unbootable_pattern': 'Hard Disk.*not a bootable disk',
                                  'image_name': 'enospc',
                                  'image_remove_command': 'rm -rf %s',
                                  'image_name_stg': 'enospc',
                                  'image_clone_command': 'cp --reflink=auto %s %s',
                                  'image_size': '10G',
                                  'images': 'image1 stg',
                                  'image_raw_device': 'no',
                                  'image_format': 'qcow2',
                                  'image_boot': 'no',
                                  'image_verify_bootable': 'yes',
                                  'image_format_stg': 'qcow2'}}


class TestParams(unittest.TestCase):

    def setUp(self):
        self.params = utils_params.Params(BASE_DICT)

    def testObjects(self):
        self.assertEquals(self.params.objects("images"), ['image1', 'stg'])

    def testObjectsParams(self):
        for key in list(CORRECT_RESULT_MAPPING.keys()):
            self.assertEquals(self.params.object_params(key),
                              CORRECT_RESULT_MAPPING[key])

    def testGetItemMissing(self):
        try:
            self.params['bogus']
            raise ValueError("Did not get a ParamNotFound error when trying "
                             "to access a non-existing param")
        # pylint: disable=E0712
        except utils_params.ParamNotFound:
            pass

    def testGetItem(self):
        self.assertEqual(self.params['image_size'], "10G")

    def testGetBoolean(self):
        self.params["foo1"] = "yes"
        self.params["foo2"] = "no"
        self.params["foo3"] = "on"
        self.params["foo4"] = "off"
        self.params["foo5"] = "true"
        self.params["foo6"] = "false"
        self.assertEqual(True, self.params.get_boolean('foo1'))
        self.assertEqual(False, self.params.get_boolean('foo2'))
        self.assertEqual(True, self.params.get_boolean('foo3'))
        self.assertEqual(False, self.params.get_boolean('foo4'))
        self.assertEqual(True, self.params.get_boolean('foo5'))
        self.assertEqual(False, self.params.get_boolean('foo6'))
        self.assertEqual(False, self.params.get_boolean('notgiven'))

    def testGetNumeric(self):
        self.params["something"] = "7"
        self.params["foobar"] = 11
        self.params["barsome"] = 13.17
        self.assertEqual(7, self.params.get_numeric('something'))
        self.assertEqual(7, self.params.get_numeric('something'), int)
        self.assertEqual(7.0, self.params.get_numeric('something'), float)
        self.assertEqual(11, self.params.get_numeric('foobar'))
        self.assertEqual(11, self.params.get_numeric('something'), int)
        self.assertEqual(11.0, self.params.get_numeric('foobar'), float)
        self.assertEqual(13, self.params.get_numeric('barsome'))
        self.assertEqual(13, self.params.get_numeric('barsome'), int)
        self.assertEqual(13.17, self.params.get_numeric('barsome'), float)
        self.assertEqual(17, self.params.get_numeric('joke', 17))
        self.assertEqual(17.13, self.params.get_numeric('joke', 17.13), float)

    def testGetList(self):
        self.params["primes"] = "7 11 13 17"
        self.params["dashed"] = "7-11-13"
        self.assertEqual(["7", "11", "13", "17"], self.params.get_list('primes'))
        self.assertEqual([7, 11, 13, 17], self.params.get_list('primes', "1 2 3", " ", int))
        self.assertEqual([1, 2, 3], self.params.get_list('missing', "1 2 3", " ", int))
        self.assertEqual([7, 11, 13], self.params.get_list('dashed', "1 2 3", "-", int))

    def testGetDict(self):
        self.params["dummy"] = "name1=value1 name2=value2"
        self.assertEqual({"name1": "value1", "name2": "value2"}, self.params.get_dict('dummy'))
        result_dict = self.params.get_dict('dummy', need_order=True)
        right_dict, wrong_dict = OrderedDict(), OrderedDict()
        right_dict["name1"] = "value1"
        right_dict["name2"] = "value2"
        wrong_dict["name2"] = "value2"
        wrong_dict["name1"] = "value1"
        self.assertEqual(right_dict, result_dict)
        self.assertNotEqual(wrong_dict, result_dict)

    def dropDictInternals(self):
        self.params["a"] = "7"
        self.params["b"] = "11"
        self.params["_b"] = "13"
        pruned = self.params.drop_dict_internals()
        self.assertIn("a", pruned.keys())
        self.assertEqual(pruned["a"], self.params["a"])
        self.assertIn("b", pruned.keys())
        self.assertEqual(pruned["b"], self.params["b"])
        self.assertNotIn("_b", pruned.keys())


if __name__ == "__main__":
    unittest.main()
