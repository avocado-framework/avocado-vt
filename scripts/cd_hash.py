#!/usr/bin/python
"""
Program that calculates several hashes for a given CD image.

:copyright: Red Hat 2008-2009
"""

import logging
import optparse
import os
import sys

from avocado.utils import crypto
from logging_config import LoggingConfig

if __name__ == "__main__":
    log_cfg = LoggingConfig(set_fmt=False)
    log_cfg.configure_logging()

    parser = optparse.OptionParser("usage: %prog [options] [filenames]")
    options, args = parser.parse_args()

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
            logging.error("File %s does not exist!", filename)
            continue
        if not can_read_file:
            logging.error("File %s does not have read permissions!", filename)
            continue

        logging.info("Hash values for file %s", os.path.basename(filename))
        logging.info(
            "    md5    (1m): %s",
            crypto.hash_file(filename, 1024 * 1024, algorithm="md5"),
        )
        logging.info(
            "    sha1   (1m): %s",
            crypto.hash_file(filename, 1024 * 1024, algorithm="sha1"),
        )
        logging.info("    md5  (full): %s", crypto.hash_file(filename, algorithm="md5"))
        logging.info(
            "    sha1 (full): %s", crypto.hash_file(filename, algorithm="sha1")
        )
