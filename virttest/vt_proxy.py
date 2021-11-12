from xmlrpc import client

from virttest.utils_agent import service_manager


class ServerProxyError(Exception):
    pass


def _importer(name, root_package=False, relative_globals=None, level=0):
    return __import__(name, locals=None, globals=relative_globals,
                      fromlist=[] if root_package else [None], level=level)


class _ClientMethod:
    def __init__(self, send, name):
        self.__send = send
        self.__name = name

    def __getattr__(self, name):
        return _ClientMethod(self.__send, "%s.%s" % (self.__name, name))

    def __call__(self, *args):
        try:
            return self.__send(self.__name, args)
        except client.Fault as e:
            if "." in e.faultCode[0]:
                root_mod = ".".join(e.faultCode[0].split(".")[:-1])
                exc_type = e.faultCode[0].split(".")[-1]
            kargs = e.faultCode[1]
            if isinstance(kargs, dict):
                raise getattr(_importer(root_mod), exc_type)(**kargs)
            elif isinstance(kargs, str):
                raise eval(e.faultCode[0])(kargs)


class _ClientServerProxy(client.ServerProxy):
    def __getattr__(self, name):
        return _ClientMethod(self._ServerProxy__request, name)


class ClientServerProxy(object):
    def __init__(self, uri):
        self._proxy = _ClientServerProxy(uri, allow_none=True,
                                         use_builtin_types=True)

    def __getattr__(self, name):
        return getattr(self._proxy, name)


class LocalServerProxy(object):
    def __init__(self):
        self._services = service_manager.init_services()

    def __getattr__(self, name):
        return self._services.get_service(name)


def get_server_proxy(uri=None):
    return ClientServerProxy(uri) if uri else LocalServerProxy()
