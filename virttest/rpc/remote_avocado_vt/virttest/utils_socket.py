import socket
import select

SOCKETS = {}


def create_socket(name):
    _socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    SOCKETS[name] = _socket


def settimeout(name, timeout):
    SOCKETS[name].settimeout(timeout)


def connect(name, file_name):
    SOCKETS[name].connect(file_name)


def shutdown(name):
    SOCKETS[name].shutdown(socket.SHUT_RDWR)


def close(name):
    SOCKETS[name].close()


def recv(name, bufsize):
    return SOCKETS[name].recv(bufsize)


# need to move it into module.
def select_select(name, timeout):
    return bool(select.select([SOCKETS[name]], [], [], timeout)[0])


def sendall(name, cmd):
    # get bytes object from Binary object
    cmd = cmd.data
    SOCKETS[name].sendall(cmd)
