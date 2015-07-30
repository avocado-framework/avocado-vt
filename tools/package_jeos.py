#!/usr/bin/python

import os
import sys
import logging
import shutil

import common
from autotest.client import utils
from autotest.client.shared import logging_manager
from virttest import utils_misc


def package_jeos(img):
    """
    Package JeOS and make it ready for upload.

    Steps:
    1) Move /path/to/jeos.qcow2 to /path/to/jeos.qcow2.backup
    2) Sparsify the image, creating a new, trimmed down /path/to/jeos.qcow2
    3) Compress the sparsified image with 7za

    :param img: Path to a qcow2 image
    """
    basedir = os.path.dirname(img)
    backup = img + '.backup'
    qemu_img = utils_misc.find_command('qemu-img')
    shutil.move(img, backup)
    logging.info("Backup %s saved", backup)

    utils.system("%s convert -f qcow2 -O qcow2 %s %s" % (qemu_img, backup, img))
    logging.info("Sparse file %s created successfully", img)

    archiver = utils_misc.find_command('7za')
    compressed_img = img + ".7z"
    utils.system("%s a %s %s" % (archiver, compressed_img, img))
    logging.info("JeOS compressed file %s created successfuly",
                 compressed_img)


if __name__ == "__main__":
    logging_manager.configure_logging(utils_misc.VirtLoggingConfig(),
                                      verbose=True)

    if len(sys.argv) <= 1:
        logging.info("Usage: %s [path to freshly installed JeOS qcow2 image]",
                     sys.argv[0])
        sys.exit(1)

    path = sys.argv[1]
    image = os.path.abspath(path)
    package_jeos(image)
