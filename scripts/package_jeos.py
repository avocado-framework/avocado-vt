#!/usr/bin/python

import logging
import os
import shutil
import sys

from avocado.utils import process

# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(basedir, "virttest")):
    sys.path.append(basedir)

from virttest import utils_misc


def package_jeos(img):
    """
    Package JeOS and make it ready for upload.

    Steps:
    1) Move /path/to/jeos.qcow2 to /path/to/jeos.qcow2.backup
    2) Sparsify the image, creating a new, trimmed down /path/to/jeos.qcow2
    3) Compress the sparsified image with xz

    :param img: Path to a qcow2 image
    """
    basedir = os.path.dirname(img)
    backup = img + ".backup"
    qemu_img = utils_misc.find_command("qemu-img")
    shutil.move(img, backup)
    logging.info("Backup %s saved", backup)

    process.system(
        "%s convert -f qcow2 -O qcow2 -o compat=0.10 %s %s" % (qemu_img, backup, img)
    )
    logging.info("Sparse file %s created successfully", img)
    compressed_img = img + ".xz"
    archiver = utils_misc.find_command("xz")
    process.system("%s -9 -e %s" % (archiver, img))
    logging.info("JeOS compressed file %s created successfuly", compressed_img)


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        print("Usage: %s [path to freshly installed JeOS qcow2 image]" % sys.argv[0])
        sys.exit(1)

    path = sys.argv[1]
    image = os.path.abspath(path)
    package_jeos(image)
