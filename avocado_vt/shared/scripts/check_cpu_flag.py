#!/usr/bin/python
import os


class check_error(Exception):
    pass


def check_cpu_flag():
    with open('/proc/cpuinfo') as info_f:
        cpuinfo = info_f.read()
    flags = os.environ['KVM_TEST_required_cpu_flags']
    for i in flags.split():
        if i not in cpuinfo:
            err_msg = "Host CPU doestn't have flag(%s)" % i
            print(err_msg)
            raise check_error(err_msg)


if __name__ == "__main__":
    check_cpu_flag()
