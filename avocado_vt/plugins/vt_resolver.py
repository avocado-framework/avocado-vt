from avocado.core.nrunner import Runnable
from avocado.core.plugin_interfaces import Resolver
from avocado.core.resolver import (ReferenceResolution,
                                   ReferenceResolutionResult)
from avocado.core.settings import settings

from ..discovery import DiscoveryMixIn


class VTResolver(Resolver, DiscoveryMixIn):

    name = 'vt'
    description = 'Test resolver for Avocado-VT tests'

    def _parameters_to_runnable(self, params):
        params = self.convert_parameters(params)
        url = params.get('name')
        vt_params = params.get('vt_params')

        # Flatten the vt_params, discarding the attributes that are not
        # scalars, and will not be used in the context of nrunner
        for key in ('_name_map_file', '_short_name_map_file', 'dep'):
            if key in vt_params:
                del(vt_params[key])

        return Runnable('avocado-vt', url, **vt_params)

    def resolve(self, reference):
        self.config = settings.as_dict()
        try:
            cartesian_parser = self._get_parser()
            self._save_parser_cartesian_config(cartesian_parser)
        except Exception as details:
            return ReferenceResolution(reference,
                                       ReferenceResolutionResult.ERROR,
                                       info=details)

        cartesian_parser.only_filter(reference)

        runnables = [self._parameters_to_runnable(d) for d in
                     cartesian_parser.get_dicts()]
        if runnables:
            return ReferenceResolution(reference,
                                       ReferenceResolutionResult.SUCCESS,
                                       runnables)
        else:
            return ReferenceResolution(reference,
                                       ReferenceResolutionResult.NOTFOUND)
