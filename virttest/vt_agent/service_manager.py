import inspect
import logging
import sys
import traceback
import os
import imp

from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.client import Fault
from xmlrpc.client import dumps
from xmlrpc.client import loads


class ServiceError(Exception):
    pass


class Services(object):
    def __init__(self):
        self._services = {}

    def register_service(self, name, service):
        self._services[name] = service

    def get_service(self, name):
        try:
            return self._services[name]
        except KeyError:
            raise ServiceError("No support service '%s'." % name)

    def __iter__(self):
        for name, service in self._services.items():
            yield name, service


def init_services(mod_dirs=["services"]):
    services = Services()
    for mod_dir in mod_dirs:
        basedir = os.path.dirname(__file__)
        services_dir = os.path.join(basedir, mod_dir)
        service_mods = [os.path.join(services_dir, m[:-3])
                        for m in os.listdir(services_dir) if m.endswith(".py")]
        modules = []

        for service in service_mods:
            f, p, d = imp.find_module(service)
            modules.append(imp.load_module(service, f, p, d))
            f.close()

        for service in modules:
            name = os.path.split(service.__dict__["__name__"])[-1]
            services.register_service(name, service)
    return services


class _CustomsSimpleXMLRPCServer(SimpleXMLRPCServer):
    def _marshaled_dispatch(self, data, dispatch_method=None, path=None):
        try:
            params, method = loads(data, use_builtin_types=self.use_builtin_types)

            # generate response
            if dispatch_method is not None:
                response = dispatch_method(method, params)
            else:
                response = self._dispatch(method, params)
            # wrap response in a singleton tuple
            response = (response,)
            response = dumps(response, methodresponse=1,
                             allow_none=self.allow_none,
                             encoding=self.encoding)
        except Fault as fault:
            response = dumps(fault, allow_none=self.allow_none,
                             encoding=self.encoding)
        except:
            # report exception back to server
            exc_type, exc_value, exc_tb = sys.exc_info()

            tb_info = traceback.format_exception(exc_type, exc_value,
                                                 exc_tb.tb_next)
            tb_info = "".join([_ for _ in tb_info])
            try:
                mod = exc_type.__dict__.get("__module__", "")
                if mod:
                    _exc_type = ".".join((mod, exc_type.__name__))
                    _exc_value = exc_value.__dict__
                else:
                    _exc_type = exc_type.__name__
                    _exc_value = str(exc_value)
                response = dumps(Fault((_exc_type, _exc_value), tb_info),
                                 encoding=self.encoding,
                                 allow_none=self.allow_none)
                logging.error(tb_info)
            finally:
                # Break reference cycle
                exc_type = exc_value = exc_tb = None

        return response.encode(self.encoding, 'xmlcharrefreplace')


class RPCServer(object):
    def __init__(self, addr=()):
        self._server = _CustomsSimpleXMLRPCServer(addr, allow_none=False,
                                                  use_builtin_types=False)

    def register_services(self, services):
        for name, service in services:
            members = [_ for _ in inspect.getmembers(service)]
            for member in members:
                member_name = member[0]
                member_obj = member[1]
                if inspect.isfunction(member_obj):
                    function_name = ".".join((name, member_name))
                    logging.info("Registers service: %s", function_name)
                    self._server.register_function(member_obj, function_name)

    def serve_forever(self):
        self._server.serve_forever()
