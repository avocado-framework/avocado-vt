import platform
ARCH = platform.machine()
DEFAULT_MACHINE_TYPE = None

if ARCH in ('ppc64', 'ppc64le'):
    DEFAULT_MACHINE_TYPE = "pseries"
elif ARCH in ('x86_64', 'i386'):
    DEFAULT_MACHINE_TYPE = "i440fx"
else:
    # TODO: Handle other supported archs
    pass


def get_default_guest_os_info():
    """
    Gets the default asset and variant information
    TODO: Check for the ARCH and choose corresponding default asset
    """
    default_asset = 'jeos-27-'
    default_asset = '%s%s' % (default_asset, ARCH)
    return {'asset': default_asset, 'variant': 'JeOS.27'}


DEFAULT_GUEST_OS = get_default_guest_os_info()['variant']

__all__ = ['DEFAULT_MACHINE_TYPE', 'DEFAULT_GUEST_OS',
           'get_default_guest_os_info']
