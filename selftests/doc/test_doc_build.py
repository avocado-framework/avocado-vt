"""
Build documentation and report whether we had warning/error messages.

This is geared towards documentation build regression testing.
"""
import os
import unittest

from avocado.utils import process


basedir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
basedir = os.path.abspath(basedir)


class DocBuildError(Exception):
    pass


class DocBuildTest(unittest.TestCase):

    def test_build_docs(self):
        """
        Build avocado VT HTML docs, reporting failures
        """
        ignore_list = ['No python imaging library installed',
                       'ovirtsdk module not present',
                       'Virsh executable not set or found on path',
                       'virt-admin executable not set or found on path',
                       "failed to import module u'virttest.passfd'",
                       "failed to import module u'virttest.step_editor'"]
        failure_lines = []
        doc_dir = os.path.join(basedir, 'docs')
        process.run('make -C %s clean' % doc_dir)
        result = process.run('make -C %s html' % doc_dir)
        stdout = result.stdout_text.splitlines()
        stderr = result.stderr_text.splitlines()
        output_lines = stdout + stderr
        for line in output_lines:
            ignore_msg = False
            for ignore in ignore_list:
                if ignore in line:
                    print('Expected warning ignored: %s' % line)
                    ignore_msg = True
            if ignore_msg:
                continue
            if 'ERROR' in line:
                failure_lines.append(line)
            if 'WARNING' in line:
                failure_lines.append(line)
        if failure_lines:
            e_msg = ('%s ERRORS and/or WARNINGS detected while building the html docs:\n' %
                     len(failure_lines))
            for (index, failure_line) in enumerate(failure_lines):
                e_msg += "%s) %s\n" % (index + 1, failure_line)
            e_msg += ('Full output: %s\n' % '\n'.join(output_lines))
            e_msg += 'Please check the output and fix your docstrings/.rst docs'
            raise DocBuildError(e_msg)


if __name__ == '__main__':
    unittest.main()
