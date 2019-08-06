#!/usr/bin/python
#
# Copyright 2010 Red Hat, Inc. and/or its affiliates.
#
# Licensed to you under the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.  See the files README and
# LICENSE_GPL_v2 which accompany this distribution.
#

import os
import struct
import platform
import optparse

try:
    import hashlib
except ImportError:
    import md5


class ShakeHandError(Exception):

    def __init__(self, msg):
        Exception.__init__(self, msg)
        self.msg = msg

    def __str__(self):
        return ("Shake hand fail. %s" % self.msg)


class Md5MissMatch(Exception):

    def __init__(self, md5_pre, md5_post):
        Exception.__init__(self, md5_pre, md5_post)
        self.md5_pre = md5_pre
        self.md5_post = md5_post

    def __str__(self):
        return ("Md5 miss match. Original md5 = %s, current md5 = %s" %
                (self.md5_pre, self.md5_post))


class VirtIoChannel:

    # Python on Windows 7 return 'Microsoft' rather than 'Windows' as documented.
    is_windows = (platform.system() == 'Windows') or (platform.system() == 'Microsoft')

    def __init__(self, device_name):
        self.ack_format = "3s"
        self.ack_msg = b"ACK"
        self.hi_format = "2s"
        self.hi_msg = b"HI"
        self.recv_msg = b'ALLRECEIVED'
        if self.is_windows:
            vport_name = '\\\\.\\Global\\' + device_name
            from windows_support import WinBufferedReadFile
            self._vport = WinBufferedReadFile(vport_name)
        else:
            vport_name = '/dev/virtio-ports/' + device_name
            self._vport = os.open(vport_name, os.O_RDWR)

    def close(self):
        if self.is_windows:
            self._vport.close()
        else:
            os.close(self._vport)

    def receive(self, size):
        if self.is_windows:
            txt = self._vport.read(size)
        else:
            txt = os.read(self._vport, size)
        return txt

    def send(self, message):
        if self.is_windows:
            self._vport.write(message)
        else:
            os.write(self._vport, message)

    def shake_hand(self, size=0, action="receive"):
        hi_msg_len = struct.calcsize(self.hi_format)
        ack_msg_len = struct.calcsize(self.ack_format)
        if action == "send":
            self.send(self.hi_msg)
            txt = self.receive(hi_msg_len)
            out = struct.unpack(self.hi_format, txt)[0]
            if out != b"HI":
                raise ShakeHandError("Fail to get HI from host.")
            size_s = struct.pack("q", size)
            self.send(size_s)
            txt = self.receive(ack_msg_len)
            ack_str = struct.unpack(self.ack_format, txt)[0]
            if ack_str != self.ack_msg:
                raise ShakeHandError("Host didn't ACK the file size message.")
            return size
        elif action == "receive":
            txt = b''
            while len(txt) < hi_msg_len:
                txt += self.receive(hi_msg_len)
            hi_str = struct.unpack(self.hi_format, txt)[0]
            if hi_str != self.hi_msg:
                raise ShakeHandError("Fail to get HI from host.")
            self.send(txt)
            size = self.receive(8)
            if size:
                size = struct.unpack("q", size)[0]
                txt = struct.pack(self.ack_format, self.ack_msg)
                self.send(txt)
            return size


def md5_init(data=None):
    """
    Returns md5. This function is implemented in order to encapsulate hash
    objects in a way that is compatible with python 2.4 and python 2.6
    without warnings.

    Note that even though python 2.6 hashlib supports hash types other than
    md5 and sha1, we are artificially limiting the input values in order to
    make the function to behave exactly the same among both python
    implementations.

    :param data: Optional input string that will be used to update the hash.
    """

    try:
        md5_value = hashlib.new("md5")
    except NameError:
        md5_value = md5.new()
    if data:
        md5_value.update(data)
    return md5_value


def get_md5(filename, size=None):
    """
    Calculate the hash of filename.
    If size is not None, limit to first size bytes.
    Throw exception if something is wrong with filename.
    Can be also implemented with bash one-liner (assuming size%1024==0):
    dd if=filename bs=1024 count=size/1024 | sha1sum -

    :param filename: Path of the file that will have its hash calculated.
    :param method: Method used to calculate the hash. Supported methods:
            * md5
            * sha1
    :return: Hash of the file, if something goes wrong, return None.
    """
    chunksize = 4096
    fsize = os.path.getsize(filename)

    if not size or size > fsize:
        size = fsize
    f = open(filename, 'rb')

    md5_value = md5_init()
    while size > 0:
        if chunksize > size:
            chunksize = size
        data = f.read(chunksize)
        if len(data) == 0:
            print("Nothing left to read but size=%d" % size)
            break
        md5_value.update(data)
        size -= len(data)
    f.close()
    return md5_value.hexdigest()


def receive(device, filename, p_size=1024):
    recv_size = 0
    vio = VirtIoChannel(device)
    size = vio.shake_hand(action="receive")
    if p_size < int(size):
        p_size = int(size)
    md5_value = md5_init()
    file_no = open(filename, 'wb')
    try:
        while recv_size < size:
            txt = vio.receive(p_size)
            md5_value.update(txt)
            file_no.write(txt)
            recv_size += len(txt)
        vio.send(vio.recv_msg)
    finally:
        file_no.close()
        if vio:
            vio.close()
    md5_sum = md5_value.hexdigest()
    return md5_sum


def send(device, filename, p_size=1024):
    send_size = 0
    f_size = os.path.getsize(filename)
    vio = VirtIoChannel(device)
    vio.shake_hand(f_size, action="send")
    md5_value = md5_init()
    file_no = open(filename, 'rb')
    try:
        while send_size < f_size:
            txt = file_no.read(p_size)
            vio.send(txt)
            md5_value.update(txt)
            send_size += len(txt)
    finally:
        print("Sent size = %s" % send_size)
        file_no.close()
        if vio:
            vio.close()
    md5_sum = md5_value.hexdigest()
    return md5_sum


if __name__ == "__main__":
    txt = "Transfer data between guest and host through virtio serial."
    parser = optparse.OptionParser(txt)

    parser.add_option("-d", "--device", dest="device",
                      help="serial device name used in qemu command"
                           "eg: -device virtserialport,chardev=x,name=redhat"
                           "need use redhat here.")
    parser.add_option("-f", "--filename", dest="filename",
                      help="File transfer to guest or save data to.")
    parser.add_option("-a", "--action", dest="action", default="send",
                      help="Send data out or receive data.")
    parser.add_option("-p", "--package", dest="package", default=1024,
                      help="Package size during file transfer.")

    options, args = parser.parse_args()

    if options.device:
        device = options.device
    else:
        parser.error("Please set -d parameter.")

    if options.filename:
        filename = options.filename
    else:
        parser.error("Please set -f parameter.")
    p_size = options.package
    action = options.action
    if action not in ("receive", "send", "both"):
        parser.error('Please set -a parameter: "receive", "send", "both"')

    if action == "receive":
        md5_sum = receive(device, filename, p_size=p_size)
        print("md5_sum = %s" % md5_sum)
    elif action == "send":
        md5_sum = send(device, filename, p_size=p_size)
        print("md5_sum = %s" % md5_sum)
    else:
        md5_ori = receive(device, filename, p_size=p_size)
        print("md5_original = %s" % md5_ori)
        md5_post = send(device, filename, p_size=p_size)
        print("md5_post = %s" % md5_post)
        if md5_ori != md5_post:
            raise Md5MissMatch(md5_ori, md5_post)
