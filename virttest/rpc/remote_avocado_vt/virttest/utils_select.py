import select

SELECTER = {}

POLLER = {}


def create_poller(name):
    poller = select.poll()
    POLLER[name] = poller


def register_poller(name, fd, eventmask=None):
    POLLER[name].register(fd, eventmask)


def poll_poller(name, timeout=None):
    return POLLER[name].poll(timeout)
