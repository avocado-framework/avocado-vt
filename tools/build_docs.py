#!/usr/bin/python
"""
Build documentation and report wether we had warning/error messages.

This is geared towards documentation build regression testing.
"""
import os
import sys
import common

from autotest.client import utils


def build_docs():
    """
    Build virt-test HTML docs, reporting failures.
    """
    ignore_list = ['No python imaging library installed',
                   'Virsh executable not set or found on path',
                   "failed to import module u'virttest.passfd'",
                   "failed to import module u'virttest.step_editor'"]
    failure_lines = []
    root_dir = common.virt_test_dir
    doc_dir = os.path.join(root_dir, 'documentation')
    output = utils.system_output('make -C %s html 2>&1' % doc_dir)
    output_lines = output.splitlines()
    for line in output_lines:
        ignore_msg = False
        for ignore in ignore_list:
            if ignore in line:
                print 'Expected warning ignored: %s' % line
                ignore_msg = True
        if ignore_msg:
            continue
        if 'ERROR' in line:
            failure_lines.append(line)
        if 'WARNING' in line:
            failure_lines.append(line)
    if failure_lines:
        print ('%s ERRORs/WARNINGs detected while building the html docs:' %
               len(failure_lines))
        for (index, failure_line) in enumerate(failure_lines):
            print "%s) %s" % (index + 1, failure_line)
        print 'Please check the output and fix your docstrings/.rst docs'
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == '__main__':
    build_docs()
