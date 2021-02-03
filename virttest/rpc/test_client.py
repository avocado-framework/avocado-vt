import xmlrpc.client
import sys

host = sys.argv[1]
port = sys.argv[2]

proxy = xmlrpc.client.ServerProxy("http://%s:%s/" % (host, int(port)),
                                  allow_none=True, use_builtin_types=True)
# try:
#     proxy.os.close(0)
# except


