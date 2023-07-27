from threading import RLock

from .objects.instance_state import States


class InstanceAPI(object):
    def __init__(self):
        self._lock = RLock()

    @staticmethod
    def _get_client_server(instance):
        return instance.node.proxy.virt.vmm

    def build_instance(self, instance):
        with self._lock:
            if not instance.state:
                client_server = self._get_client_server(instance)
                client_server.build_instance(instance.uuid,
                                             instance.kind,
                                             instance.spec)
                instance.state = States.DEFINED
            else:
                raise

    def run_instance(self, instance):
        with self._lock:
            if instance.state == States.DEFINED:
                client_server = self._get_client_server(instance)
                client_server.run_instance(instance.uuid)
                instance.state = States.RUNNING
            else:
                raise

    def stop_instance(self, instance, graceful=True, timeout=120, shutdown_cmd=None,
                      username=None, password=None, prompt=None):
        with self._lock:
            if instance.state in (States.RUNNING, States.PAUSED):
                client_server = self._get_client_server(instance)
                client_server.stop_instance(instance.uuid, graceful, timeout,
                                            shutdown_cmd, username, password,
                                            prompt)
                instance.state = States.STOPPED
            else:
                raise

    def pause_instance(self, instance):
        with self._lock:
            if instance.state == States.RUNNING:
                client_server = self._get_client_server(instance)
                client_server.pause_instance(instance.uuid)
                instance.state = States.PAUSED
            else:
                raise

    def continue_instance(self, instance):
        with self._lock:
            if instance.state == States.PAUSED:
                client_server = self._get_client_server(instance)
                client_server.continue_instance(instance.uuid)
                instance.state = States.RUNNING
            else:
                raise

    def undefine_instance(self, instance, free_mac_addresses=True):
        with self._lock:
            if instance.state == States.STOPPED:
                client_server = self._get_client_server(instance)
                client_server.cleanup_instance(instance.uuid, free_mac_addresses)
                instance.state = States.UNDEFINED
            else:
                raise

    def get_monitor_consoles(self, instance):
        client_server = self._get_client_server(instance)
        return client_server.get_instance_consoles(instance.uuid, "monitor")

    def get_serial_consoles(self, instance):
        client_server = self._get_client_server(instance)
        return client_server.get_instance_consoles(instance.uuid, "serial")

    def get_vnc_consoles(self, instance):
        raise NotImplementedError

    def get_process_info(self, instance, name):
        client_server = self._get_client_server(instance)
        return client_server.get_instance_process(instance.uuid, name)

    def get_pid(self, instance):
        client_server = self._get_client_server(instance)
        return client_server.get_instance_pid(instance.uuid)

    def migrate_instance(self, instance, dest_node):
        pass
