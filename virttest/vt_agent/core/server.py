# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2024
# Authors: Yongxue Hong <yhong@redhat.com>

import inspect
import logging
import sys
import traceback
from xmlrpc.client import Fault, dumps, loads
from xmlrpc.server import SimpleXMLRPCServer

from .. import api

LOG = logging.getLogger("avocado.agent." + __name__)


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
            response = dumps(
                response,
                methodresponse=1,
                allow_none=self.allow_none,
                encoding=self.encoding,
            )
        except Fault as fault:
            response = dumps(fault, allow_none=self.allow_none, encoding=self.encoding)
        except:
            # report exception back to server
            exc_type, exc_value, exc_tb = sys.exc_info()

            tb_info = traceback.format_exception(exc_type, exc_value, exc_tb.tb_next)
            tb_info = "".join([_ for _ in tb_info])
            try:
                mod = exc_type.__dict__.get("__module__", "")
                if mod:
                    _exc_type = ".".join((mod, exc_type.__name__))
                    _exc_value = exc_value.__dict__
                else:
                    _exc_type = exc_type.__name__
                    _exc_value = str(exc_value)
                response = dumps(
                    Fault((_exc_type, _exc_value), tb_info),
                    encoding=self.encoding,
                    allow_none=self.allow_none,
                )
                logging.error(tb_info)
            finally:
                pass

        return response.encode(self.encoding, "xmlcharrefreplace")


class RPCServer(object):
    def __init__(self, addr=()):
        self._server = _CustomsSimpleXMLRPCServer(
            addr, allow_none=True, use_builtin_types=False
        )
        self._load_server_api()

    def _load_server_api(self):
        for m in inspect.getmembers(api):
            if inspect.isfunction(m[1]):
                name = ".".join(
                    (".".join(api.__dict__["__name__"].split(".")[1:]), m[0])
                )
                self._server.register_function(m[1], name)

    def register_services(self, services):
        service_list = []
        for name, service in services:
            service_list.append(name)
            members = [_ for _ in inspect.getmembers(service)]
            for member in members:
                member_name = member[0]
                member_obj = member[1]
                if inspect.isfunction(member_obj):
                    function_name = ".".join((name, member_name))
                    self._server.register_function(member_obj, function_name)
        services = ", ".join([_ for _ in service_list])
        LOG.info("Services registered: %s" % services)

    def serve_forever(self):
        self._server.serve_forever()
