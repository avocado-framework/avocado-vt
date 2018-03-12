from virttest.utils_test.base_check_version import base_check_python_version
try:
    from virttest.utils_test.site_check_version import site_check_python_version
except ImportError:
    class site_check_python_version:
        pass


class check_python_version(site_check_python_version,
                           base_check_python_version):
    pass
