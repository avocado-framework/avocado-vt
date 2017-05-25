import os

from avocado.utils import path as utils_path

from . import data_dir
from . import cartesian_config

GUEST_NAME_LIST = None
TAG_INDEX = {}


def _variant_only_file(filename):
    """
    Parse file containing flat list of items to append on an 'only' filter
    """
    if not os.path.isabs(filename):
        filename = os.path.realpath(os.path.join(data_dir.get_root_dir(),
                                                 filename))
    return ", ".join([_.strip() for _ in open(filename)
                      if not _.lstrip().startswith('#')])


SUPPORTED_TEST_TYPES = [
    'qemu', 'libvirt', 'libguestfs', 'openvswitch', 'v2v', 'lvsb', 'spice']

SUPPORTED_LIBVIRT_URIS = ['qemu:///system', 'lxc:///']
SUPPORTED_LIBVIRT_DRIVERS = ['qemu', 'lxc', 'xen']

SUPPORTED_IMAGE_TYPES = ['raw', 'qcow2', 'qed', 'vmdk']
SUPPORTED_DISK_BUSES = ['ide', 'scsi', 'virtio_blk',
                        'virtio_scsi', 'lsi_scsi', 'ahci', 'usb2', 'xenblk']
SUPPORTED_NIC_MODELS = ["virtio_net", "e1000", "rtl8139", "spapr-vlan"]
SUPPORTED_NET_TYPES = ["bridge", "user", "none"]


def find_default_qemu_paths(options_qemu=None, options_dst_qemu=None):
    """
    This function returns qemu-related paths. It's not trying to be smart as
    the real paths are discovered later in utils_misc.get_qemu_img_binary().
    :param options_qemu: User defined qemu-bin path
    :param options_dst_qemu: User defined destination VM qemu-bin path
    :return: qemu_path, qemu_img_path, qemu_io_path, qemu_dst_bin_path
    """
    if options_qemu:
        qemu_bin_path = options_qemu
    else:
        try:
            qemu_bin_path = utils_path.find_command('qemu-kvm')
        except utils_path.CmdNotFoundError:
            qemu_bin_path = utils_path.find_command('kvm')

    if options_dst_qemu is not None:
        qemu_dst_bin_path = options_dst_qemu
    else:
        qemu_dst_bin_path = None

    qemu_dirname = os.path.dirname(qemu_bin_path)
    qemu_img_path = os.path.join(qemu_dirname, 'qemu-img')
    qemu_io_path = os.path.join(qemu_dirname, 'qemu-io')

    return [qemu_bin_path, qemu_img_path, qemu_io_path, qemu_dst_bin_path]


def get_cartesian_parser_details(cartesian_parser):
    """
    Print detailed information about filters applied to the cartesian cfg.

    :param cartesian_parser: Cartesian parser object.
    """
    details = ""
    details += ("Tests produced by config file %s\n\n" %
                cartesian_parser.filename)

    details += "The full test list was modified by the following:\n\n"

    if cartesian_parser.only_filters:
        details += "Filters applied:\n"
        for flt in cartesian_parser.only_filters:
            details += "    %s\n" % flt

    if cartesian_parser.no_filters:
        for flt in cartesian_parser.no_filters:
            details += "    %s\n" % flt

    details += "\n"
    details += "Different guest OS have different test lists\n"
    details += "\n"

    if cartesian_parser.assignments:
        details += "Assignments applied:\n"
        for flt in cartesian_parser.assignments:
            details += "    %s\n" % flt

    details += "\n"
    details += "Assignments override values previously set in the config file\n"
    details += "\n"

    return details


def get_guest_name_parser(options):
    cartesian_parser = cartesian_config.Parser()
    machines_cfg_path = data_dir.get_backend_cfg_path(options.vt_type,
                                                      'machines.cfg')
    guest_os_cfg_path = data_dir.get_backend_cfg_path(options.vt_type,
                                                      'guest-os.cfg')
    cartesian_parser.parse_file(machines_cfg_path)
    cartesian_parser.parse_file(guest_os_cfg_path)
    if options.vt_arch:
        cartesian_parser.only_filter(options.vt_arch)
    if options.vt_machine_type:
        cartesian_parser.only_filter(options.vt_machine_type)
    if options.vt_guest_os:
        cartesian_parser.only_filter(options.vt_guest_os)
    return cartesian_parser


def get_guest_name_list(options):
    global GUEST_NAME_LIST
    if GUEST_NAME_LIST is None:
        guest_name_list = []
        for params in get_guest_name_parser(options).get_dicts():
            shortname = ".".join(params['name'].split(".")[1:])
            guest_name_list.append(shortname)

        GUEST_NAME_LIST = guest_name_list

    return GUEST_NAME_LIST
