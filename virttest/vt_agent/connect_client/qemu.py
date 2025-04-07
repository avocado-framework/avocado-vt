import logging
import os

from vt_agent.core.data_dir import LOG_DIR

from virttest.vt_monitor import client

LOG = logging.getLogger("avocado.service." + __name__)


def create_connect_client(instance_id, name, protocol, client_params, log_file=None):
    backend = client_params.get("backend")

    if log_file is None:
        log_file = "%s-instance-%s.log" % (name, instance_id)
        log_file = os.path.join(LOG_DIR, log_file)

    if backend == "socket":
        host = client_params.get("host")
        port = client_params.get("port")
        path = client_params.get("path")
        if host and port:
            address = (host, port)
            backend_type = "tcp_socket"
        elif path:
            address = path
            backend_type = "unix_socket"
        else:
            raise ValueError("No address specified for connect client")
    else:
        raise NotImplementedError("Not support connect backend type %s" % backend)

    if protocol == "qmp":
        return client.QMPMonitor(instance_id, name, backend_type, address, log_file)
    elif protocol == "hmp":
        return client.HumanMonitor(instance_id, name, backend_type, address, log_file)
    else:
        raise NotImplementedError("Unsupported connect protocol %s" % protocol)
