import logging

from ...resmgr import Resource, ResMgr


LOG = logging.getLogger('avocado.' + __name__)


class CVMResMgrError(Exception):
    pass


class SEVResource(Resource):
    TYPE = 'sev'

    def _to_attributes(self, resource_params):
        pass

    @property
    def requests(self):
        return {'type': self.TYPE}


class SNPResource(Resource):
    TYPE = 'snp'

    def _to_attributes(self, resource_params):
        pass

    @property
    def requests(self):
        return {'type': self.TYPE}


class TDXResource(Resource):
    TYPE = 'tdx'

    def _to_attributes(self, resource_params):
        pass

    @property
    def requests(self):
        return {'type': self.TYPE}


class CVMResMgr(ResMgr):

    def _initialize(self, config):
        pass

    def check_resource_managed(self, spec):
        pass

    def _get_resource_type(self, spec):
        return spec['type']

    def is_cvm_supported(node_uuid):
        """
        Check if the platform supports CVM
        """
        node = get_node(node_uuid)
        return node.proxy.is_cvm_supported()

    def enabled(self, resource_type, node_uuid):
        """
        Check if the platform supports a specific CVM type
        e.g. a AMD SEV/SNP machine cannot allocate a TDX resource
        """
        node = get_node(node_uuid)
        return node.proxy.enabled(resource_type)


_cvm_resmgr = CVMResMgr()
