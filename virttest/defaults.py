DEFAULT_MACHINE_TYPE = "i440fx"


def get_default_guest_os_info():
    """
    Gets the default asset and variant information
    """
    return {'asset': 'jeos-21-64', 'variant': 'JeOS.21'}


DEFAULT_GUEST_OS = get_default_guest_os_info()['variant']

__all__ = ['DEFAULT_MACHINE_TYPE', 'DEFAULT_GUEST_OS',
           'get_default_guest_os_info']
