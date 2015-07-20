#!/usr/bin/python
"""
Program that calculates several hashes for a given CD image.

:copyright: Red Hat 2008-2009
"""

import os
import sys
import optparse

from avocado.utils import crypto
from avocado.core import output
from avocado.core import log


if __name__ == "__main__":
    parser = optparse.OptionParser("usage: %prog [options] [filenames]")
    options, args = parser.parse_args()

    log.configure()
    view = output.View()

    if args:
        filenames = args
    else:
        parser.print_help()
        sys.exit(1)

    for filename in filenames:
        filename = os.path.abspath(filename)

        file_exists = os.path.isfile(filename)
        can_read_file = os.access(filename, os.R_OK)
        if not file_exists:
            view.notify(event='error', msg="File %s does not exist!" % filename)
            continue
        if not can_read_file:
            view.notify(event='error',
                        msg="File %s does not have read permissions!" % filename)
            continue

        view.notify(event='message', msg="Hash values for file %s" % os.path.basename(filename))
        view.notify(event='minor', msg="md5    (1m): %s" % crypto.hash_file(filename, 1024 * 1024, algorithm="md5"))
        view.notify(event='minor', msg="sha1   (1m): %s" % crypto.hash_file(filename, 1024 * 1024, algorithm="sha1"))
        view.notify(event='minor', msg="md5  (full): %s" % crypto.hash_file(filename, algorithm="md5"))
        view.notify(event='minor', msg="sha1 (full): %s" % crypto.hash_file(filename, algorithm="sha1"))
