import warnings

from avocado.core.plugin_interfaces import Discoverer, Resolver
from avocado.core.resolver import ReferenceResolution, ReferenceResolutionResult
from avocado.core.settings import settings

from ..discovery import DiscoveryMixIn

try:
    from avocado.core.nrunner import Runnable
except ImportError:
    from avocado.core.nrunner.runnable import Runnable


class VTResolverUtils(DiscoveryMixIn):
    def __init__(self, config):
        self.config = config or settings.as_dict()

    def _parameters_to_runnable(self, params):
        params = self.convert_parameters(params)
        uri = params.get("name")
        vt_params = params.get("vt_params")

        # Flatten the vt_params, discarding the attributes that are not
        # scalars, and will not be used in the context of nrunner
        for key in ("_name_map_file", "_short_name_map_file", "dep"):
            if key in vt_params:
                del vt_params[key]

        return Runnable("avocado-vt", uri, **vt_params)

    def _get_reference_resolution(self, reference):
        cartesian_parser = self._get_parser()
        self._save_parser_cartesian_config(cartesian_parser)

        if reference != "":
            cartesian_parser.only_filter(reference)

        runnables = [
            self._parameters_to_runnable(d) for d in cartesian_parser.get_dicts()
        ]
        if runnables:
            if (
                self.config.get(
                    "run.max_parallel_tasks",
                    self.config.get("nrunner.max_parallel_tasks", 1),
                )
                != 1
            ):
                if (
                    self.config.get(
                        "run.spawner", self.config.get("nrunner.spawner", "process")
                    )
                    != "lxc"
                ):
                    warnings.warn(
                        "The VT NextRunner can be run only "
                        "with max-parallel-tasks set to 1 with a process "
                        "spawner, did you forget to use an LXC spawner?"
                    )
            return ReferenceResolution(
                reference, ReferenceResolutionResult.SUCCESS, runnables
            )
        else:
            return ReferenceResolution(reference, ReferenceResolutionResult.NOTFOUND)


class VTResolver(VTResolverUtils, Resolver):

    name = "vt"
    description = "Test resolver for Avocado-VT tests"

    def resolve(self, reference):
        """
        It will resolve vt test references into resolutions.

        It discovers the tests from cartesian config based on the specification
        from the user.
        """
        return self._get_reference_resolution(reference)


class VTDiscoverer(Discoverer, VTResolverUtils):

    name = "vt-discoverer"
    description = "Test discoverer for Avocado-VT tests"

    def discover(self):
        """It will discover vt test resolutions from cartesian config."""
        self.config = self.config or settings.as_dict()

        return [self._get_reference_resolution("")]
