#!/usr/bin/python
"""
Download helper for blobs needed for virt testing.

Downloads blobs defined in assets. Assets are .ini files that contain the
    following config keys:

    title: Title string to display in the download progress bar.
    url = URL of the resource
    sha1_url = URL with SHA1 information for the resource, in the form
        sha1sum file_basename
    destination = Location of your file relative to the data directory
        (TEST_SUITE_ROOT/shared/data)
    destination_uncompressed (optional) = Location of the uncompressed file
        relative to the data directory (TEST_SUITE_ROOT/shared/data)
    uncompress_cmd (optionl) = Command that needs to be executed with the
        compressed file as a parameter

:copyright: Red Hat 2012
"""
import glob
import os
import sys
import logging
import time
import common
from autotest.client.shared import logging_manager
from virttest import asset, utils_misc


def download_assets():
    all_assets = asset.get_all_assets()
    if all_assets:
        logging.info("Available download assets:")
        logging.info("")
        for asset_info in all_assets:
            asset_keys = asset_info.keys()
            logging.info("%d - %s" % (all_assets.index(asset_info) + 1,
                                      asset_info['title']))
            asset_keys.pop(asset_keys.index('title'))
            asset_keys.sort()
            for k in asset_keys:
                logging.info("    %s = %s" % (k, asset_info[k]))
            logging.info("")
    indexes = raw_input("%s INFO | Type the index for the assets you want to "
                        "download (comma separated, Ctrl+C to abort): " %
                        time.strftime("%H:%M:%S", time.localtime()))

    index_list = []

    for idx in indexes.split(","):
        try:
            index = int(idx) - 1
            index_list.append(index)
            all_assets[index]
        except (ValueError, IndexError):
            logging.error("Invalid index(es), aborting...")
            sys.exit(1)

    for idx in index_list:
        asset_info = all_assets[idx]
        asset.download_file(asset_info, interactive=True)

if __name__ == "__main__":
    logging_manager.configure_logging(utils_misc.VirtLoggingConfig())
    try:
        download_assets()
    except KeyboardInterrupt:
        print
        logging.info("Aborting...")
        sys.exit(0)
