import re
import logging
import platform
import time


from avocado.utils import process
from virttest.compat_52lts import decode_to_text


ARCH = platform.machine()


def get_load_per(session=None, iterations=2, interval=10.0):
    """
    Get the percentage of load in Guest/Host
    :param session: Guest Sesssion
    :param iterations: iterations
    :param interval: interval between load calculation
    :return: load of system in percentage
    """
    idle_secs = []
    idle_per = []
    cmd = "cat /proc/uptime"
    for itr in range(iterations):
        if session:
            idle_secs.append(float(session.cmd_output(cmd).strip().split()[1]))
        else:
            idle_secs.append(float(process.system_output(cmd).split()[1]))
        time.sleep(interval)
    for itr in range(iterations - 1):
        idle_per.append((idle_secs[itr + 1] - idle_secs[itr]) / interval)
    return int((1 - (sum(idle_per) / len(idle_per))) * 100)


def get_thread_cpu(thread):
    """
    Get the light weight process(thread) used cpus.

    :param thread: thread checked
    :type thread: string
    :return: A list include all cpus the thread used
    :rtype: builtin.list
    """
    cmd = "ps -o cpuid,lwp -eL | grep -w %s$" % thread
    cpu_thread = decode_to_text(process.system_output(cmd, shell=True))
    if not cpu_thread:
        return []
    return list(set([_.strip().split()[0] for _ in cpu_thread.splitlines()]))


def get_pid_cpu(pid):
    """
    Get the process used cpus.

    :param pid: process id
    :type thread: string
    :return: A list include all cpus the process used
    :rtype: builtin.list
    """
    cmd = "ps -o cpuid -L -p %s" % pid
    cpu_pid = decode_to_text(process.system_output(cmd))
    if not cpu_pid:
        return []
    return list(set([_.strip() for _ in cpu_pid.splitlines()]))


def get_cpu_info(session=None):
    """
    Return information about the CPU architecture

    :param session: session Object
    :return: A dirt of cpu information
    """
    cpu_info = {}
    cmd = "lscpu"
    if session is None:
        output = decode_to_text(process.system_output(cmd, ignore_status=True)).splitlines()
    else:
        try:
            output = session.cmd_output(cmd).splitlines()
        finally:
            session.close()
    cpu_info = dict(map(lambda x: [i.strip() for i in x.split(":")], output))
    return cpu_info


def get_cpu_flags(cpu_info=""):
    """
    Returns a list of the CPU flags
    """
    cpu_flags_re = "flags\s+:\s+([\w\s]+)\n"
    if not cpu_info:
        fd = open("/proc/cpuinfo")
        cpu_info = fd.read()
        fd.close()
    cpu_flag_lists = re.findall(cpu_flags_re, cpu_info)
    if not cpu_flag_lists:
        return []
    cpu_flags = cpu_flag_lists[0]
    return re.split("\s+", cpu_flags.strip())


def get_cpu_vendor(cpu_info="", verbose=True):
    """
    Returns the name of the CPU vendor
    """
    vendor_re = "vendor_id\s+:\s+(\w+)"
    if not cpu_info:
        fd = open("/proc/cpuinfo")
        cpu_info = fd.read()
        fd.close()
    vendor = re.findall(vendor_re, cpu_info)
    if not vendor:
        vendor = 'unknown'
    else:
        vendor = vendor[0]
    if verbose:
        logging.debug("Detected CPU vendor as '%s'", vendor)
    return vendor


def get_host_cpu_models():
    """
    Get cpu model from host cpuinfo
    """
    def _cpu_flags_sort(cpu_flags):
        """
        Update the cpu flags get from host to a certain order and format
        """
        flag_list = sorted(re.split("\s+", cpu_flags.strip()))
        cpu_flags = " ".join(flag_list)
        return cpu_flags

    def _make_up_pattern(flags):
        """
        Update the check pattern to a certain order and format
        """
        pattern_list = sorted(re.split(",", flags.strip()))
        pattern = r"(\b%s\b)" % pattern_list[0]
        for i in pattern_list[1:]:
            pattern += r".+(\b%s\b)" % i
        return pattern

    if ARCH in ('ppc64', 'ppc64le'):
        return []     # remove -cpu and leave it on qemu to decide

    cpu_types = {"AuthenticAMD": ["EPYC", "Opteron_G5", "Opteron_G4",
                                  "Opteron_G3", "Opteron_G2", "Opteron_G1"],
                 "GenuineIntel": ["KnightsMill", "Icelake-Server",
                                  "Icelake-Client", "Cascadelake-Server",
                                  "Skylake-Server", "Skylake-Client",
                                  "Broadwell", "Broadwell-noTSX",
                                  "Haswell", "Haswell-noTSX", "IvyBridge",
                                  "SandyBridge", "Westmere", "Nehalem",
                                  "Penryn", "Conroe"]}
    cpu_type_re = {"EPYC": "avx2,adx,bmi2,sha_ni",
                   "Opteron_G5": "f16c,fma4,xop,tbm",
                   "Opteron_G4": ("fma4,xop,avx,xsave,aes,sse4.2|sse4_2,"
                                  "sse4.1|sse4_1,cx16,ssse3,sse4a"),
                   "Opteron_G3": "cx16,sse4a",
                   "Opteron_G2": "cx16",
                   "Opteron_G1": "",
                   "KnightsMill": "avx512_4vnniw,avx512pf,avx512er",
                   "Icelake-Server": "avx512_vnni,la57,clflushopt",
                   "Icelake-Client": ("avx512_vpopcntdq|avx512-vpopcntdq,"
                                      "avx512vbmi,avx512_vbmi2|avx512vbmi2,"
                                      "gfni,vaes,vpclmulqdq,avx512_vnni"),
                   "Cascadelake-Server": ("avx512f,avx512dq,avx512bw,avx512cd,"
                                          "avx512vl,clflushopt,avx512_vnni"),
                   "Skylake-Server": "mpx,avx512f,clwb,xgetbv1,pcid",
                   "Skylake-Client": "mpx,xgetbv1,pcid",
                   "Broadwell": "adx,rdseed,3dnowprefetch,hle",
                   "Broadwell-noTSX": "adx,rdseed,3dnowprefetch",
                   "Haswell": "fma,avx2,movbe,hle",
                   "Haswell-noTSX": "fma,avx2,movbe",
                   "IvyBridge": "f16c,fsgsbase,erms",
                   "SandyBridge": ("avx,xsave,aes,sse4_2|sse4.2,sse4.1|sse4_1,"
                                   "cx16,ssse3"),
                   "Westmere": "aes,sse4.2|sse4_2,sse4.1|sse4_1,cx16,ssse3",
                   "Nehalem": "sse4.2|sse4_2,sse4.1|sse4_1,cx16,ssse3",
                   "Penryn": "sse4.1|sse4_1,cx16,ssse3",
                   "Conroe": "ssse3"}

    fd = open("/proc/cpuinfo")
    cpu_info = fd.read()
    fd.close()

    cpu_flags = " ".join(get_cpu_flags(cpu_info))
    vendor = get_cpu_vendor(cpu_info)

    cpu_model = None
    cpu_support_model = []
    if cpu_flags:
        cpu_flags = _cpu_flags_sort(cpu_flags)
        for cpu_type in cpu_types.get(vendor):
            pattern = _make_up_pattern(cpu_type_re.get(cpu_type))
            if re.findall(pattern, cpu_flags):
                cpu_model = cpu_type
                cpu_support_model.append(cpu_model)
    else:
        logging.warn("Can not Get cpu flags from cpuinfo")

    return cpu_support_model
