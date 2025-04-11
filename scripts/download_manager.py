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
    uncompress_cmd (optional) = Command that needs to be executed with the
        compressed file as a parameter

:copyright: Red Hat 2012
"""
import logging
import os
import sys

# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(basedir, "virttest")):
    sys.path.append(basedir)

from avocado.core.output import TERM_SUPPORT
from logging_config import LoggingConfig
from six.moves import input, urllib

from virttest import asset


def download_assets():
    all_assets = asset.get_all_assets()
    all_assets_sorted = []
    if all_assets:
        logging.info("Available download assets:")
        title_list = [a["title"] for a in all_assets]
        for index, title in enumerate(sorted(title_list)):
            asset_info = [a for a in all_assets if a["title"] == title][0]
            all_assets_sorted.append(asset_info)
            asset_present_str = TERM_SUPPORT.partial_str("Missing")
            if asset_info["asset_exists"]:
                asset_present_str = TERM_SUPPORT.healthy_str("Present")
            asset_msg = "%s - [%s] %s (%s)" % (
                index + 1,
                asset_present_str,
                TERM_SUPPORT.header_str(asset_info["title"]),
                asset_info["destination"],
            )
            logging.info(asset_msg)
    indexes = input(
        "Type the index for the assets you want to "
        "download (comma separated, leave empty to abort): "
    )

    index_list = []

    for idx in indexes.split(","):
        try:
            assert int(idx) > 0
            index = int(idx) - 1
            index_list.append(index)
            all_assets_sorted[index]
        except (ValueError, IndexError, AssertionError):
            logging.error("Invalid index(es), aborting...")
            sys.exit(1)

    for idx in index_list:
        asset_info = all_assets_sorted[idx]
        try:
            asset.download_file(asset_info, interactive=True)
        except urllib.error.HTTPError as http_error:
            logging.error("HTTP Error %s: URL %s", http_error.code, asset_info["url"])
            os.remove(asset_info["destination"])


if __name__ == "__main__":
    log_cfg = LoggingConfig(set_fmt=False)
    log_cfg.configure_logging()

    try:
        download_assets()
    except KeyboardInterrupt:
        logging.info("Aborting...")
        sys.exit(1)
