#!/usr/bin/env python
"""
Script to fetch test status info from sqlit data base. Before use this
script, avocado We must be launch with '--journal' option.
"""

from __future__ import division

import argparse
import os
import sqlite3
import sys

import six
from avocado.core import data_dir
from dateutil import parser as dateparser
from six.moves import xrange


def colour_result(result):
    """Colour result in the test status info"""
    colours_map = {
        "PASS": "\033[92mPASS\033[00m",
        "ERROR": "\033[93mERROR\033[00m",
        "FAIL": "\033[91mFAIL\033[00m",
    }
    return colours_map.get(result) or result


def summarise_records(records):
    """Summarise test records and print it in cyan"""
    num_row = len(records[0])
    rows = tuple([("row%s" % x) for x in xrange(num_row)])
    records_summary = {}
    for rows in records:
        records_summary[rows[1]] = records_summary.get(rows[1], 0) + 1
        records_summary[rows[4]] = records_summary.get(rows[4], 0) + 1
    res = ", ".join(
        "%s=%r" % (key, val) for (key, val) in six.iteritems(records_summary)
    )
    print("\033[96mSummary: \n" + res + "\033[00m")


def get_total_seconds(td):
    """Alias for get total_seconds in python2.6"""
    if hasattr(td, "total_seconds"):
        return td.total_seconds()
    return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 1e6) // 1e6


def fetch_data(db_file=".journal.sqlite"):
    """Fetch tests status info from journal database"""
    records = []
    con = sqlite3.connect(db_file)
    try:
        cur = con.cursor()
        cur.execute("select tag, time, action, status  from test_journal")
        while True:
            # First record contains start info, second contains end info
            # merged start info and end info into one record.
            data = cur.fetchmany(2)
            if not data:
                break
            tag = data[0][0]
            result = "N/A"
            status = "Running"
            end_time = None
            end_str = None
            elapsed = None
            start_time = dateparser.parse(data[0][1])
            start_str = start_time.strftime("%Y-%m-%d %X")
            if len(data) > 1:
                status = "Finshed"
                result = data[1][3]
                end_time = dateparser.parse(data[1][1])
                time_delta = end_time - start_time
                elapsed = get_total_seconds(time_delta)
                end_str = end_time.strftime("%Y-%m-%d %X")
            record = (tag, status, start_str, end_str, result, elapsed)
            records.append(record)
    finally:
        con.close()
    return records


def print_data(records, skip_timestamp=False):
    """Print formatted tests status info"""
    if not records:
        return
    if not skip_timestamp:
        print(
            "%-40s %-15s %-15s %-15s %-10s %-10s"
            % ("CaseName", "Status", "StartTime", "EndTime", "Result", "TimeElapsed")
        )
    else:
        print("%-40s %-15s %-10s" % ("CaseName", "Status", "Result"))
    for row in records:
        if not skip_timestamp:
            print(
                "%s %s %s %s %s %s"
                % (row[0], row[1], row[2], row[3], colour_result(row[4]), row[5])
            )
        else:
            print("%s %s %s" % (row[0], row[1], colour_result(row[4])))
    summarise_records(records)


if __name__ == "__main__":
    default_results_dir = os.path.join(data_dir.get_logs_dir(), "latest")
    parser = argparse.ArgumentParser(description="Avocado journal dump tool")
    parser.add_argument(
        "-d",
        "--test-results-dir",
        action="store",
        default=default_results_dir,
        dest="results_dir",
        help="avocado test results dir, Default: %s" % default_results_dir,
    )
    parser.add_argument(
        "-s",
        "--skip-timestamp",
        action="store_true",
        default=False,
        dest="skip_timestamp",
        help="skip timestamp output (leaving status and result enabled)",
    )
    parser.add_argument("-v", "--version", action="version", version="%(prog)s 1.0")
    arguments = parser.parse_args()
    db_file = os.path.join(arguments.results_dir, ".journal.sqlite")
    if not os.path.isfile(db_file):
        print("`.journal.sqlite` DB not found in results directory, ")
        print("Please start avocado with option '--journal'.")
        parser.print_help()
        sys.exit(1)
    data = fetch_data(db_file)
    print_data(data, arguments.skip_timestamp)
