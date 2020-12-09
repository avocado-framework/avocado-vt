from avocado.core.plugin_interfaces import CLICmd
from avocado.core.settings import settings
from virttest.compat import add_option, is_registering_settings_required
from virttest.standalone_test import get_guest_name_parser

from ..loader import guest_listing


class VTListGuests(CLICmd):

    """
    Avocado VT - implements vt-list-guests command
    """

    name = 'vt-list-guests'
    description = "Avocado-VT 'vt-list-guests' command"

    def configure(self, parser):
        parser = super(VTListGuests, self).configure(parser)

        # [vt.list_guests] section
        section = 'vt.list_guests'

        key = 'guest_os'
        if is_registering_settings_required():
            settings.register_option(section, key=key, default=None,
                                     help_msg='List only specific guests')

        namespace = "%s.%s" % (section, key)
        add_option(parser=parser, dest=namespace, arg='--guest-os')

        # Also expose the --vt-type option, as the guests depend on it
        add_option(parser=parser, dest='vt.type', arg='--vt-type')

    def run(self, config):
        guest_name_parser = get_guest_name_parser(
            config,
            guest_os='vt.list_guests.guest_os')
        guest_listing(config, guest_name_parser)
