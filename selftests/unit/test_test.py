#!/usr/bin/env python

import argparse
import os
import sys

if sys.version_info[:2] == (2, 6):
    import unittest2 as unittest
else:
    import unittest

# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(basedir, 'virttest')):
    sys.path.append(basedir)

from avocado_vt import test as vt_test


class FakeJob(object):

    def __init__(self):
        self.args = argparse.Namespace()
        self.args.vt_config = True

FAKE_PARAMS = {'shortname': 'fake',
               'vm_type': 'fake'}


class VirtTestTest(unittest.TestCase):

    def test_datadir(self):
        test = vt_test.VirtTest(job=FakeJob(),
                                params=FAKE_PARAMS)
        self.assertIsNone(test.datadir)

if __name__ == '__main__':
    unittest.main()
