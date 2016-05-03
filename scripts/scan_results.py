#!/usr/bin/env python
"""
Script to fetch test status info from sqlit data base. Before use this
script, avocado We must be lanuch with '--journal' option.
"""

import os
import sys
import sqlite3
import argparse
from avocado.core import data_dir
from dateutil import parser as dateparser


def get_total_seconds(td):
    """ Alias for get total_seconds in python2.6 """
    if hasattr(td, 'total_seconds'):
        return td.total_seconds()
    return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 1e6) / 1e6


def fetch_data(db_file=".journal.sqlite"):
    """ Fetch tests status info from journal database"""
    records = []
    con = sqlite3.connect(db_file)
    try:
        cur = con.cursor()
        cur.execute("select tag, time, action, status  from test_journal")
        while True:
            # First record contation start info, second contain end info
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
    """ Print formated tests status info"""
    if not records:
        return
    if not skip_timestamp:
        print "%-40s %-15s %-15s %-15s %-10s %-10s" % (
            "CaseName", "Status", "StartTime",
            "EndTime", "Result", "TimeElapsed")
    else:
        print "%-40s %-15s %-10s" % ("CaseName", "Status", "Result")
    for row in records:
        if not skip_timestamp:
            print "%s %s %s %s %s %s" % row
        else:
            print "%s %s %s" % (row[0], row[1], row[4])


if __name__ == "__main__":
    default_results_dir = os.path.join(data_dir.get_logs_dir(), 'latest')
    parser = argparse.ArgumentParser(description="Avocado journal dump tool")
    parser.add_argument(
        '-d',
        '--test-results-dir',
        action='store',
        default=default_results_dir,
        dest='results_dir',
        help="avocado test results dir, Default: %s" %
        default_results_dir)
    parser.add_argument(
        '-s',
        '--skip-timestamp',
        action='store_true',
        default=False,
        dest='skip_timestamp',
        help="skip timestamp output (leaving status and result enabled)")
    parser.add_argument(
        '-v',
        '--version',
        action='version',
        version='%(prog)s 1.0')
    arguments = parser.parse_args()
    db_file = os.path.join(arguments.results_dir, '.journal.sqlite')
    if not os.path.isfile(db_file):
        print "`.journal.sqlite` DB not found in results directory, "
        print "Please start avocado with option '--journal'."
        parser.print_help()
        sys.exit(1)
    data = fetch_data(db_file)
    print_data(data, arguments.skip_timestamp)
