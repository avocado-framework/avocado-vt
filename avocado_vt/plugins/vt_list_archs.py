from avocado.core.plugin_interfaces import CLICmd
from virttest.compat import add_option
from virttest.standalone_test import get_guest_name_parser

from ..loader import arch_listing


class VTListArchs(CLICmd):

    """
    Avocado VT - implements vt-list-archs command
    """

    name = 'vt-list-archs'
    description = "Avocado-VT 'vt-list-archs' command"

    def configure(self, parser):
        parser = super(VTListArchs, self).configure(parser)
        # Expose the --vt-type option, as the archs definitions depend on it
        add_option(parser=parser, dest='vt.type', arg='--vt-type')

    def run(self, config):
        guest_name_parser = get_guest_name_parser(config,
                                                  arch=None,
                                                  machine=None)
        arch_listing(config, guest_name_parser)
