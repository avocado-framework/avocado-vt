import platform

from avocado.utils import cpu

ARCH = platform.machine()

if ARCH in ('ppc64', 'ppc64le'):
    # From include/linux/sockios.h
    SIOCSIFHWADDR = 0x8924
    SIOCGIFHWADDR = 0x8927
    SIOCGIFFLAGS = 0x8913
    SIOCSIFFLAGS = 0x8914
    SIOCGIFADDR = 0x8915
    SIOCSIFADDR = 0x8916
    SIOCGIFNETMASK = 0x891B
    SIOCSIFNETMASK = 0x891C
    SIOCGIFMTU = 0x8921
    SIOCSIFMTU = 0x8922
    SIOCGIFINDEX = 0x8933
    SIOCBRADDIF = 0x89a2
    SIOCBRDELIF = 0x89a3
    SIOCBRADDBR = 0x89a0
    SIOCBRDELBR = 0x89a1
    # From linux/include/linux/if_tun.h
    TUNSETIFF = 0x800454ca
    TUNGETIFF = 0x400454d2
    TUNGETFEATURES = 0x400454cf
    TUNSETQUEUE = 0x800454d9
    IFF_MULTI_QUEUE = 0x0100
    IFF_TAP = 0x2
    IFF_NO_PI = 0x1000
    IFF_VNET_HDR = 0x4000
    # From linux/include/linux/if.h
    IFF_UP = 0x1
    IFF_PROMISC = 0x100
    # From linux/netlink.h
    NETLINK_ROUTE = 0
    NLM_F_REQUEST = 1
    NLM_F_ACK = 4
    RTM_DELLINK = 17
    NLMSG_ERROR = 2
    # From linux/socket.h
    AF_PACKET = 17
    # From linux/vhost.h
    VHOST_VSOCK_SET_GUEST_CID = 0x8008af60
else:
    # From include/linux/sockios.h
    SIOCSIFHWADDR = 0x8924
    SIOCGIFHWADDR = 0x8927
    SIOCGIFFLAGS = 0x8913
    SIOCSIFFLAGS = 0x8914
    SIOCGIFADDR = 0x8915
    SIOCSIFADDR = 0x8916
    SIOCGIFNETMASK = 0x891B
    SIOCSIFNETMASK = 0x891C
    SIOCGIFMTU = 0x8921
    SIOCSIFMTU = 0x8922
    SIOCGIFINDEX = 0x8933
    SIOCBRADDIF = 0x89a2
    SIOCBRDELIF = 0x89a3
    SIOCBRADDBR = 0x89a0
    SIOCBRDELBR = 0x89a1
    # From linux/include/linux/if_tun.h
    TUNSETIFF = 0x400454ca
    TUNGETIFF = 0x800454d2
    TUNGETFEATURES = 0x800454cf
    TUNSETQUEUE = 0x400454d9
    IFF_MULTI_QUEUE = 0x0100
    IFF_TAP = 0x0002
    IFF_NO_PI = 0x1000
    IFF_VNET_HDR = 0x4000
    # From linux/include/linux/if.h
    IFF_UP = 0x1
    IFF_PROMISC = 0x100
    # From linux/netlink.h
    NETLINK_ROUTE = 0
    NLM_F_REQUEST = 1
    NLM_F_ACK = 4
    RTM_DELLINK = 17
    NLMSG_ERROR = 2
    # From linux/socket.h
    AF_PACKET = 17
    # From linux/vhost.h
    VHOST_VSOCK_SET_GUEST_CID = 0x4008af60


def get_kvm_module_list():
    if ARCH == 'x86_64':
        vendor = cpu.get_vendor() if hasattr(cpu, 'get_vendor') else cpu.get_cpu_vendor_name()
        return ["kvm", "kvm-%s" % vendor]
    elif ARCH in ('ppc64', 'ppc64le'):
        # FIXME: Please correct it if anyone still want to use KVM-PR mode
        return ["kvm", "kvm-hv"]
    elif ARCH in ('s390', 's390x'):
        return ["kvm"]
    elif ARCH == "aarch64":
        return []
