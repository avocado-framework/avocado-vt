import subprocess
import inspect
import os
import sys
import shutil
import socket

from xmlrpc.server import SimpleXMLRPCServer

import utils_netifaces

from remote_avocado.utils import process as remote_avocado_utils_process
from remote_avocado.utils import path as remote_avocado_utils_path
from remote_avocado.utils import crypto as remote_avocado_utils_crypto

from remote_avocado_vt.virttest import utils_net as remote_avocado_vt_virttest_utils_net
from remote_avocado_vt.virttest import data_dir as remote_avocado_vt_virttest_data_dir
from remote_avocado_vt.virttest import utils_misc as remote_avocado_vt_virttest_utils_misc
from remote_avocado_vt.virttest import utils_net
from remote_avocado_vt.virttest import utils_socket as remote_avocado_vt_virttest_utils_socket
from remote_avocado_vt.virttest import utils_select as remote_avocado_vt_virttest_utils_select
from remote_avocado_vt.virttest import ppm_utils as remote_avocado_vt_virttest_ppm_utils
from remote_avocado_vt.virttest import utils_env_process as remote_avocado_vt_virttest_utils_env_process

from remote_aexpect.utils import factory as remote_aexpect_utils_factory
from remote_aexpect.utils import astring as remote_aexpect_utils_astring
from remote_aexpect.utils import genio as remote_aexpect_utils_genio
from remote_aexpect.utils import path as remote_aexpect_utils_path
from remote_aexpect.utils import process as remote_aexpect_utils_process
from remote_aexpect.utils import wait as remote_aexpect_utils_wait
from remote_aexpect.utils import client as remote_aexpect_utils_client
from remote_aexpect import shared as remote_aexpect_shared

host = sys.argv[1]
port = sys.argv[2]


def aexpect_subprocess_popoen(pass_fds=None, a_id=None, encoding=None,
                              echo=None, readers=None, command=None):
    helper_cmd = remote_aexpect_utils_path.find_command('aexpect_helper')

    try:
        sub = subprocess.Popen([helper_cmd],
                               shell=True,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,
                               pass_fds=pass_fds)
    except Exception as e:
        print(str(e))
        return str(e)

    # Send parameters to the server
    sub.stdin.write(("%s\n" % a_id).encode(encoding))
    sub.stdin.write(("%s\n" % echo).encode(encoding))
    readers = "%s\n" % ",".join(readers)
    sub.stdin.write(readers.encode(encoding))
    sub.stdin.write(("%s\n" % command).encode(encoding))
    sub.stdin.flush()
    # Wait for the server to complete its initialization
    while 1:
        out = sub.stdout.readline().decode(encoding, "ignore")
        if out:
            if "Server %s ready" % a_id in out:
                break


server = SimpleXMLRPCServer((host, int(port)), allow_none=True, logRequests=False)
print("Listening on port %s..." % port)

functions = [o for o in inspect.getmembers(os) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'os.%s' % f[0])

functions = [o for o in inspect.getmembers(os.path) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'os.path.%s' % f[0])

functions = [o for o in inspect.getmembers(shutil) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'shutil.%s' % f[0])

functions = [o for o in inspect.getmembers(socket) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'socket.%s' % f[0])

server.register_function(os.listdir, 'os.listdir')
server.register_function(os.open, 'os.open')
server.register_function(os.close, 'os.close')
server.register_function(os.read, 'os.read')
server.register_function(os.unlink, 'os.unlink')

functions = [o for o in inspect.getmembers(
        remote_aexpect_utils_factory) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'aexpect.utils.date_factory.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_aexpect_utils_astring) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'aexpect.utils.astring.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_aexpect_utils_genio) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'aexpect.utils.genio.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_aexpect_utils_path) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'aexpect.utils.path.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_aexpect_utils_process) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'aexpect.utils.process.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_aexpect_utils_wait) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'aexpect.utils.wait.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_aexpect_shared) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'aexpect.shared.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_aexpect_utils_client) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'aexpect.utils.client.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_avocado_utils_process) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'avocado.utils.process.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_avocado_utils_path) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'avocado.utils.path.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_avocado_utils_crypto) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'avocado.utils.crypto.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_avocado_vt_virttest_utils_net) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'avocado_vt.virttest.utils_net.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_avocado_vt_virttest_data_dir) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'avocado_vt.virttest.data_dir.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_avocado_vt_virttest_utils_misc) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'avocado_vt.virttest.utils_misc.%s' % f[0])

server.register_instance(utils_net.Bridge(), allow_dotted_names=True)

functions = [o for o in inspect.getmembers(
        remote_avocado_vt_virttest_utils_socket) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'avocado_vt.virttest.utils_socket.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_avocado_vt_virttest_utils_select) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'avocado_vt.virttest.utils_select.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_avocado_vt_virttest_ppm_utils) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'avocado_vt.virttest.ppm_utils.%s' % f[0])

functions = [o for o in inspect.getmembers(
        remote_avocado_vt_virttest_utils_env_process) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'avocado_vt.virttest.utils_env_process.%s' % f[0])

functions = [o for o in inspect.getmembers(utils_netifaces) if inspect.isfunction(o[1])]
for f in functions:
    server.register_function(f[1], 'utils_netifaces.%s' % f[0])

server.register_function(aexpect_subprocess_popoen, 'aexpect.subprocess.Popen')
server.serve_forever()
