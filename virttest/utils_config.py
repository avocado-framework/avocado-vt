import ast
import logging
import os.path
import ConfigParser
import StringIO


class ConfigError(Exception):

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class ConfigNoOptionError(ConfigError):

    def __init__(self, option, path):
        self.option = option
        self.path = path

    def __str__(self):
        return "There's no option %s in config file %s." % (
            self.option, self.path)


class LibvirtConfigUnknownKeyTypeError(ConfigError):

    def __init__(self, key, key_type):
        self.key = key
        self.key_type = key_type

    def __str__(self):
        return "Unknown type %s for key %s." % (self.key, self.key_type)


class LibvirtConfigUnknownKeyError(ConfigError):

    def __init__(self, key):
        self.key = key

    def __str__(self):
        return 'Unknown config key %s' % self.key


class SectionlessConfig(object):

    """
    This is a wrapper class for python's internal library ConfigParser except
    allows manipulating sectionless configuration file with a dict-like way.

    Example config file test.conf:

    ># This is a comment line.
    >a = 1
    >b = [hi, there]
    >c = hello
    >d = "hi, there"
    >e = [hi,
    >    there]

    Example script using `try...finally...` statement:

    >>> from virttest import utils_config
    >>> config = utils_config.SectionlessConfig('test.conf')
    >>> try:
    ...     print len(config)
    ...     print config
    ...     print config['a']
    ...     del config['a']
    ...     config['f'] = 'test'
    ...     print config
    ... finally:
    ...     config.restore()

    Example script using `with` statement:

    >>> from virttest import utils_config
    >>> with utils_config.SectionlessConfig('test.conf') as config:
    ...     print len(config)
    ...     print config
    ...     print config['a']
    ...     del config['a']
    ...     config['f'] = 'test'
    ...     print config
    """

    def __init__(self, path):
        self.path = path
        self.parser = ConfigParser.ConfigParser()
        # Prevent of converting option names to lower case
        self.parser.optionxform = str
        self.backup_content = open(path, 'r').read()
        read_fp = StringIO.StringIO('[root]\n' + self.backup_content)
        self.parser.readfp(read_fp)

    def __sync_file(self):
        out_file = open(self.path, 'w')
        try:
            out_file.write(self.__str__())
        finally:
            out_file.close()

    def __len__(self):
        return len(self.parser.items('root'))

    def __getitem__(self, option):
        try:
            return self.parser.get('root', option)
        except ConfigParser.NoOptionError:
            raise ConfigNoOptionError(option, self.path)

    def __setitem__(self, option, value):
        self.parser.set('root', option, value)
        self.__sync_file()

    def __delitem__(self, option):
        res = self.parser.remove_option('root', option)
        if res:
            self.__sync_file()
        else:
            raise ConfigNoOptionError(option, self.path)

    def __contains__(self, item):
        return self.parser.has_option('root', item)

    def __str__(self):
        write_fp = StringIO.StringIO()
        self.parser.write(write_fp)
        return write_fp.getvalue().split('\n', 1)[1]

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.restore()

    def restore(self):
        out_file = open(self.path, 'w')
        try:
            out_file.write(self.backup_content)
        finally:
            out_file.close()

    def set_raw(self, option, value):
        self[option] = "%s" % value

    def set_string(self, option, value):
        self[option] = '"%s"' % value

    def set_int(self, option, value):
        self[option] = '%d' % int(value)

    def set_float(self, option, value):
        self[option] = '%s' % float(value)

    def set_boolean(self, option, value):
        if type(value) == str:
            value = int(value)
        if bool(value):
            self[option] = '1'
        else:
            self[option] = '0'

    def set_list(self, option, value):
        # TODO: line separation
        value = ['"%s"' % i for i in list(value)]
        self[option] = '[%s]' % ', '.join(value)

    def get_raw(self, option):
        return self[option]

    def get_string(self, option):
        raw_str = self[option].strip()
        if raw_str.startswith('"') and raw_str.endswith('"'):
            raw_str = raw_str[1:-1]
        elif raw_str.startswith("'") and raw_str.endswith("'"):
            raw_str = raw_str[1:-1]
        else:
            raise ValueError("Invalid value for string: %s" % raw_str)
        return raw_str

    def get_int(self, option):
        return int(self.get_raw(option))

    def get_float(self, option):
        return float(self.get_raw(option))

    def get_boolean(self, option):
        try:
            bool_str = self.get_string(option).lower()
        except ValueError:
            bool_str = str(self.get_int(option))

        if bool_str in ["1", "yes", "true", "on"]:
            return True
        if bool_str in ["0", "no", "false", "off"]:
            return False
        raise ValueError("Invalid value for boolean: %s" % bool_str)

    def get_list(self, option):
        list_str = self.get_raw(option)
        return [str(i) for i in ast.literal_eval(list_str)]


class LibvirtConfigCommon(SectionlessConfig):

    """
    A abstract class to manipulate options of a libvirt related configure files
    in a property's way.

    Variables "__option_types__" and "conf_path" must be setup in the
    inherented classes before use.

    "__option_types__" is a dict contains every possible option as keys and
    their type ("boolean", "int", "string", "float" or "list") as values.

    Basic usage:
    1) Create a config file object:
    >>> # LibvirtdConfig is a subclass of LibvirtConfigCommon.
    >>> config = LibvirtdConfig()

    2) Set or update an option:
    >>> config.listen_tcp = True
    >>> config.listen_tcp = 1
    >>> config.listen_tcp = "1" # All three have the same effect.

    >>> # If the setting value don't meet the specified type.
    >>> config.listen_tcp = "invalid"
    >>> # It'll thown an warning message and set a raw string instead.

    >>> # Use set_* methods when need to customize the result.
    >>> config.set_raw("'1'")

    3) Get an option:
    >>> is_listening = config.listen_tcp
    >>> print is_listening
    True

    4) Delete an option from the config file:
    >>> del config.listen_tcp

    5) Make the changes take effect in libvirt by restart libvirt daemon.
    >>> from virttest import utils_libvirtd
    >>> utils_libvirtd.Libvirtd().restart()

    6) Restore the content of the config file.
    >>> config.restore()
    """
    __option_types__ = {}
    conf_path = ''

    def __init__(self, path=''):
        if path:
            self.conf_path = path
        if not self.conf_path:
            raise ConfigError("Path for config file is not set up.")
        if not self.__option_types__:
            raise ConfigError("__option_types__ is not set up.")
        if not os.path.isfile(self.conf_path):
            raise ConfigError("Path for config file %s don't exists."
                              % self.conf_path)
        super(LibvirtConfigCommon, self).__init__(self.conf_path)

    def __getattr__(self, key):
        if key in self.__option_types__:
            key_type = self.__option_types__[key]
            if key_type not in ['boolean', 'int', 'float', 'string', 'list']:
                raise LibvirtConfigUnknownKeyTypeError(key, key_type)
            else:
                get_func = eval('self.get_' + key_type)
                try:
                    return get_func(key)
                except ConfigNoOptionError:
                    return None
        else:
            raise LibvirtConfigUnknownKeyError(key)

    def __setattr__(self, key, value):
        if key in self.__option_types__:
            key_type = self.__option_types__[key]
            if key_type not in ['boolean', 'int', 'float', 'string', 'list']:
                raise LibvirtConfigUnknownKeyTypeError(key, key_type)
            else:
                set_func = eval('self.set_' + key_type)
                try:
                    set_func(key, value)
                except ValueError:
                    logging.warning("Key %s might not have type %s. Set raw "
                                    "string instead.", key, key_type)
                    self.set_raw(key, value)
        super(LibvirtConfigCommon, self).__setattr__(key, value)

    def __delattr__(self, key):
        if key in self.__option_types__:
            key_type = self.__option_types__[key]
            if key_type not in ['boolean', 'int', 'float', 'string', 'list']:
                raise LibvirtConfigUnknownKeyTypeError(key, key_type)
            else:
                try:
                    del self[key]
                except ConfigNoOptionError:
                    pass
                super(LibvirtConfigCommon, self).__setattr__(key, None)
        else:
            raise LibvirtConfigUnknownKeyError(key)


class LibvirtdConfig(LibvirtConfigCommon):

    """
    Class for libvirt daemon config file.
    """
    conf_path = '/etc/libvirt/libvirtd.conf'
    __option_types__ = {
        'listen_tls': 'boolean',
        'listen_tcp': 'boolean',
        'tls_port': 'string',
        'tcp_port': 'string',
        'listen_addr': 'string',
        'mdns_adv': 'boolean',
        'mdns_name': 'string',
        'unix_sock_group': 'string',
        'unix_sock_ro_perms': 'string',
        'unix_sock_rw_perms': 'string',
        'unix_sock_dir': 'string',
        'auth_unix_ro': 'string',
        'auth_unix_rw': 'string',
        'auth_tcp': 'string',
        'auth_tls': 'string',
        'access_drivers': 'list',
        'key_file': 'string',
        'cert_file': 'string',
        'ca_file': 'string',
        'crl_file': 'string',
        'tls_no_sanity_certificate': 'boolean',
        'tls_no_verify_certificate': 'boolean',
        'tls_allowed_dn_list': 'list',
        'sasl_allowed_username_list': 'list',
        'max_clients': 'int',
        'max_queued_clients': 'int',
        'min_workers': 'int',
        'max_workers': 'int',
        'prio_workers': 'int',
        'max_requests': 'int',
        'max_client_requests': 'int',
        'log_level': 'int',
        'log_filters': 'string',
        'log_outputs': 'string',
        'log_buffer_size': 'int',
        'audit_level': 'int',
        'audit_logging': 'int',
        'host_uuid': 'string',
        'keepalive_interval': 'int',
        'keepalive_count': 'int',
        'keepalive_required': 'boolean',
    }


class LibvirtQemuConfig(LibvirtConfigCommon):

    """
    Class for libvirt qemu config file.
    """
    conf_path = '/etc/libvirt/qemu.conf'
    __option_types__ = {
        'vnc_listen': 'string',
        'vnc_auto_unix_socket': 'boolean',
        'vnc_tls': 'boolean',
        'vnc_tls_x509_cert_dir': 'string',
        'vnc_tls_x509_verify': 'boolean',
        'vnc_password': 'string',
        'vnc_sasl': 'boolean',
        'vnc_sasl_dir': 'string',
        'vnc_allow_host_audio': 'boolean',
        'spice_listen': 'string',
        'spice_tls': 'boolean',
        'spice_tls_x509_cert_dir': 'string',
        'spice_password': 'string',
        'remote_display_port_min': 'int',
        'remote_display_port_max': 'int',
        'remote_websocket_port_min': 'int',
        'remote_websocket_port_max': 'int',
        'security_driver': 'list',
        'security_default_confined': 'boolean',
        'security_require_confined': 'boolean',
        'user': 'string',
        'group': 'string',
        'dynamic_ownership': 'boolean',
        'cgroup_controllers': 'list',
        'cgroup_device_acl': 'list',
        'save_image_format': 'string',
        'dump_image_format': 'string',
        'snapshot_image_format': 'string',
        'auto_dump_path': 'string',
        'auto_dump_bypass_cache': 'boolean',
        'auto_start_bypass_cache': 'boolean',
        'hugetlbfs_mount': 'list',
        'bridge_helper': 'string',
        'clear_emulator_capabilities': 'boolean',
        'set_process_name': 'boolean',
        'max_processes': 'int',
        'max_files': 'int',
        'mac_filter': 'boolean',
        'relaxed_acs_check': 'boolean',
        'allow_disk_format_probing': 'boolean',
        'lock_manager': 'string',
        'max_queued': 'int',
        'keepalive_interval': 'int',
        'keepalive_count': 'int',
        'seccomp_sandbox': 'int',
        'migration_address': 'string',
        'migration_port_min': 'int',
        'migration_port_max': 'int',
    }


class LibvirtdSysConfig(LibvirtConfigCommon):

    """
    Class for sysconfig libvirtd config file.
    """
    conf_path = '/etc/sysconfig/libvirtd'
    __option_types__ = {
        'LIBVIRTD_CONFIG': 'string',
        'LIBVIRTD_ARGS': 'string',
        'KRB5_KTNAME': 'string',
        'QEMU_AUDIO_DRV': 'string',
        'SDL_AUDIODRIVER': 'string',
        'LIBVIRTD_NOFILES_LIMIT': 'int',
    }


class LibvirtGuestsConfig(LibvirtConfigCommon):

    """
    Class for sysconfig libvirt-guests config file.
    """
    conf_path = '/etc/sysconfig/libvirt-guests'
    __option_types__ = {
        'URIS': 'string',
        'ON_BOOT': 'string',
        'START_DELAY': 'int',
        'ON_SHUTDOWN': 'string',
        'PARALLEL_SHUTDOWN': 'int',
        'SHUTDOWN_TIMEOUT': 'int',
        'BYPASS_CACHE': 'boolean'
    }
