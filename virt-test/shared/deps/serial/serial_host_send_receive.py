#!/usr/bin/python

import os
import socket
import struct
import optparse

try:
    import hashlib
except ImportError:
    import md5


class Md5MissMatch(Exception):

    def __init__(self, md5_pre, md5_post):
        Exception.__init__(self, md5_pre, md5_post)
        self.md5_pre = md5_pre
        self.md5_post = md5_post

    def __str__(self):
        return ("Md5 miss match. Original md5 = %s, current md5 = %s" %
                (self.md5_pre, self.md5_post))


class ShakeHandError(Exception):

    def __init__(self, msg):
        Exception.__init__(self, msg)
        self.msg = msg

    def __str__(self):
        return ("Shake hand fail. %s" % self.msg)


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


def shake_hand(connect, size=0, action="receive"):
    hi_str = struct.pack("2s", "HI")
    hi_str_len = len(hi_str)
    if action == "send":
        connect.send(hi_str)
        txt = connect.recv(hi_str_len)
        hi_str = struct.unpack("2s", txt)[0]
        if hi_str != "HI":
            raise ShakeHandError("Fail to get HI from guest.")
        size_str = struct.pack("q", size)
        connect.send(size_str)
        txt = connect.recv(3)
        ack_str = struct.unpack("3s", txt)[0]
        if ack_str != "ACK":
            raise ShakeHandError("Guest did not ACK the file size message.")
        return size
    elif action == "receive":
        txt = connect.recv(hi_str_len)
        hi_str = struct.unpack("2s", txt)[0]
        if hi_str != "HI":
            raise ShakeHandError("Fail to get HI from guest.")
        connect.send(hi_str)
        size = connect.recv(8)
        if size:
            size = struct.unpack("q", size)[0]
            txt = struct.pack("3s", "ACK")
            connect.send(txt)
        return size


def receive(connect, filename, p_size=1024):
    recv_size = 0
    size = shake_hand(connect, action="receive")
    if p_size < int(size):
        p_szie = int(size)
    md5_value = md5_init()
    file_no = open(filename, 'wb')
    try:
        while recv_size < size:
            txt = connect.recv(p_size)
            file_no.write(txt)
            md5_value.update(txt)
            recv_size += len(txt)
    finally:
        file_no.close()
    md5_sum = md5_value.hexdigest()
    return md5_sum


def send(connect, filename, p_size=1024):
    recv_size = 0
    f_size = os.path.getsize(filename)
    shake_hand(connect, f_size, action="send")
    md5_value = md5_init()
    file_no = open(filename, 'rb')
    try:
        while recv_size < f_size:
            txt = file_no.read(p_size)
            connect.send(txt)
            md5_value.update(txt)
            recv_size += len(txt)
    finally:
        print("received size = %s" % recv_size)
        file_no.close()
    md5_sum = md5_value.hexdigest()
    return md5_sum


def main():
    parser = optparse.OptionParser("Transfer data between guest and host"
                                   "through virtio serial. Please make sure"
                                   "VirtIOChannel.py run in guest first.")
    parser.add_option("-s", "--socket", dest="socket",
                      help="unix socket device used in qemu command"
                           "eg:your CLI:-chardev socket,id=channel2,"
                           "path=/tmp/helloworld2 ,then input"
                           "'/tmp/helloworld2' here")
    parser.add_option("-f", "--filename", dest="filename",
                      help="File transfer to guest or save data to.")
    parser.add_option("-a", "--action", dest="action", default="send",
                      help="Send data out or receive data.")
    parser.add_option("-p", "--package", dest="package", default=1024,
                      help="Package size during file transfer.")

    options, args = parser.parse_args()

    if options.socket:
        sock = options.socket
    else:
        parser.error("Please set -s parameter.")

    if options.filename:
        filename = options.filename
    else:
        parser.error("Please set -f parameter.")
    action = options.action
    p_size = options.package

    vport = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    vport.connect(sock)
    if action == "receive":
        md5_sum = receive(vport, filename, p_size=p_size)
        print("md5_sum = %s" % md5_sum)
    elif action == "send":
        md5_sum = send(vport, filename, p_size=p_size)
        print("md5_sum = %s" % md5_sum)
    else:
        md5_ori = send(vport, filename, p_size=p_size)
        print("md5_original = %s" % md5_ori)
        md5_post = receive(vport, filename, p_size=p_size)
        print("md5_post = %s" % md5_post)
        if md5_ori != md5_post:
            raise Md5MissMatch(md5_ori, md5_post)


if __name__ == "__main__":
    main()
