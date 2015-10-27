from avocado.utils import distro

DEFAULT_MACHINE_TYPE = "i440fx"
DEFAULT_GUEST_OS = None     # populated below


def get_default_guest_os_info():
    """
    Gets the default asset and variant information
    """
    return {'asset': 'jeos-21-64', 'variant': 'JeOS.21'}


DEFAULT_GUEST_OS = get_default_guest_os_info()['variant']
