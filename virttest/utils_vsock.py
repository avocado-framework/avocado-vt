import os
import fcntl
import struct
import errno

from virttest import arch

VSOCK_PATH = '/dev/vhost-vsock'


def get_guest_cid(guest_cid):
    """
    Get an unused guest cid from system

    :param guest_cid: Requested guest cid
    :return Available guest cid
    """
    vsock_fd = os.open(VSOCK_PATH, os.O_RDWR)
    try:
        while guest_cid:
            cid_c = struct.pack('L', guest_cid)
            try:
                fcntl.ioctl(
                    vsock_fd, arch.VHOST_VSOCK_SET_GUEST_CID, cid_c)
            except IOError as e:
                if e.errno == errno.EADDRINUSE:
                    guest_cid += 1
                    continue
                else:
                    raise e
            else:
                return guest_cid
    finally:
        os.close(vsock_fd)
