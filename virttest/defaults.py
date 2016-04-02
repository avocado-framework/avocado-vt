import platform
ARCH = platform.machine()
# Set the default machine to i440fx for unidentifed arch also
# Below line can be removed once support for all possible arch is covered
DEFAULT_MACHINE_TYPE = "i440fx"

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
    return {'asset': 'jeos-21-64', 'variant': 'JeOS.21'}


DEFAULT_GUEST_OS = get_default_guest_os_info()['variant']

__all__ = ['DEFAULT_MACHINE_TYPE', 'DEFAULT_GUEST_OS',
           'get_default_guest_os_info']
