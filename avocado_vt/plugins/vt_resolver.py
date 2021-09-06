import warnings

from avocado.core.nrunner import Runnable
from avocado.core.plugin_interfaces import Discoverer, Resolver
from avocado.core.resolver import (ReferenceResolution,
                                   ReferenceResolutionResult)
from avocado.core.settings import settings
from virttest.compat import get_opt

from ..discovery import DiscoveryMixIn


class VTResolverUtils(DiscoveryMixIn):

    def __init__(self, config):
        self.config = config or settings.as_dict()
        self.cartesian_parser = self._get_parser()
        self._save_parser_cartesian_config(self.cartesian_parser)

    def _parameters_to_runnable(self, params):
        params = self.convert_parameters(params)
        uri = params.get('name')
        vt_params = params.get('vt_params')

        # Flatten the vt_params, discarding the attributes that are not
        # scalars, and will not be used in the context of nrunner
        for key in ('_name_map_file', '_short_name_map_file', 'dep'):
            if key in vt_params:
                del(vt_params[key])

        return Runnable('avocado-vt', uri, **vt_params)

    def _get_reference_resolution(self, reference):
        if reference != '':
            self.cartesian_parser.only_filter(reference)

        runnables = [self._parameters_to_runnable(d) for d in
                     self.cartesian_parser.get_dicts()]
        if runnables:
            warnings.warn("The VT NextRunner is experimental and doesn't have "
                          "current Avocado VT features")
            if self.config.get("nrunner.max_parallel_tasks", 1) != 1:
                warnings.warn("The VT NextRunner can be run only with "
                              "nrunner-max-parallel-tasks set to 1")
            return ReferenceResolution(reference,
                                       ReferenceResolutionResult.SUCCESS,
                                       runnables)
        else:
            return ReferenceResolution(reference,
                                       ReferenceResolutionResult.NOTFOUND)


class VTResolver(VTResolverUtils, Resolver):

    name = 'vt'
    description = 'Test resolver for Avocado-VT tests'

    def resolve(self, reference):
        """
        It will resolve vt test references into resolutions.

        It discovers the tests from cartesian config based on the specification
        from the user.
        """
        return self._get_reference_resolution(reference)


class VTDiscoverer(VTResolverUtils, Discoverer):

    name = 'vt-discoverer'
    description = 'Test discoverer for Avocado-VT tests'

    def discover(self):
        """It will discover vt test resolutions from cartesian config."""
        self.config = settings.as_dict()
        if (not get_opt(self.config, 'vt.config') and
                not get_opt(self.config, 'list.resolver')):
            return ReferenceResolution('', ReferenceResolutionResult.NOTFOUND)

        return [self._get_reference_resolution('')]
