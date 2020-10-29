#!/usr/bin/python
"""
:author Amos Kong <akong@redhat.com>

"""
import os
import sys

if len(sys.argv) < 4:
    print(""" netperf agent usage:
    %s [session_number] [netperf_path] [netperf_parameters_str]

    $session_number: number of client sessions
    $netperf_path: client path
    $netperf_parameter_str: netperf parameters string""" % sys.argv[0])
    sys.exit()

n = int(sys.argv[1])
path = sys.argv[2]
params = " ".join(sys.argv[3:])

for i in range(n - 1):
    os.system("%s %s &" % (path, params))
os.system("%s %s" % (path, params))
