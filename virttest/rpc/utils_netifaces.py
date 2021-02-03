import netifaces


def get_ifaddresses(ifname=None, ver=None):
    return netifaces.ifaddresses(ifname).get(ver)
