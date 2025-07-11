class ComputeAPI(object):
    def __init__(self):
        pass

    @staticmethod
    def _get_client_server(node):
        return node.proxy.compute

    def get_avail_mem(self, node):
        client = self._get_client_server(node)
        return client.get_avail_mem()

    def get_hypervisor_info(self, node):
        client = self._get_client_server(node)
        return client.get_hypervisor_info()

    def get_cpu_info(self, node):
        client = self._get_client_server(node)
        return client.get_cpu_info()
