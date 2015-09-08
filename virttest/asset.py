import urllib2
import logging
import os
import re
import string
import types
import glob
import ConfigParser
import StringIO
import commands
import distutils.dir_util

from avocado.utils import process
from avocado.utils import genio
from avocado.utils import crypto
from avocado.utils import download
from avocado.utils import git

from . import data_dir


class ConfigLoader:

    """
    Base class of the configuration parser
    """

    def __init__(self, cfg, tmpdir='/tmp', raise_errors=False):
        """
        Instantiate ConfigParser and provide the file like object that we'll
        use to read configuration data from.
        :param cfg: Where we'll get configuration data. It can be either:
                * A URL containing the file
                * A valid file path inside the filesystem
                * A string containing configuration data
        :param tmpdir: Where we'll dump the temporary conf files.
        :param raise_errors: Whether config value absences will raise
                ValueError exceptions.
        """
        # Base Parser
        self.parser = ConfigParser.ConfigParser()
        # Raise errors when lacking values
        self.raise_errors = raise_errors
        # File is already a file like object
        if hasattr(cfg, 'read'):
            self.cfg = cfg
            self.parser.readfp(self.cfg)
        elif isinstance(cfg, types.StringTypes):
            # Config file is a URL. Download it to a temp dir
            if cfg.startswith('http') or cfg.startswith('ftp'):
                self.cfg = os.path.join(tmpdir, os.path.basename(cfg))
                download.url_download(cfg, self.cfg)
                self.parser.read(self.cfg)
            # Config is a valid filesystem path to a file.
            elif os.path.exists(os.path.abspath(cfg)):
                if os.path.isfile(cfg):
                    self.cfg = os.path.abspath(cfg)
                    self.parser.read(self.cfg)
                else:
                    e_msg = 'Invalid config file path: %s' % cfg
                    raise IOError(e_msg)
            # Config file is just a string, convert it to a python file like
            # object using StringIO
            else:
                self.cfg = StringIO.StringIO(cfg)
                self.parser.readfp(self.cfg)

    def get(self, section, option, default=None):
        """
        Get the value of a option.

        Section of the config file and the option name.
        You can pass a default value if the option doesn't exist.

        :param section: Configuration file section.
        :param option: Option we're looking after.
        :default: In case the option is not available and raise_errors is set
                to False, return the default.
        """
        if not self.parser.has_option(section, option):
            if self.raise_errors:
                raise ValueError('No value for option %s. Please check your '
                                 'config file "%s".' % (option, self.cfg))
            else:
                return default

        return self.parser.get(section, option)

    def set(self, section, option, value):
        """
        Set an option.

        This change is not persistent unless saved with 'save()'.
        """
        if not self.parser.has_section(section):
            self.parser.add_section(section)
        return self.parser.set(section, option, value)

    def remove(self, section, option):
        """
        Remove an option.
        """
        if self.parser.has_section(section):
            self.parser.remove_option(section, option)

    def save(self):
        """
        Save the configuration file with all modifications
        """
        if not self.cfg:
            return
        fileobj = file(self.cfg, 'w')
        try:
            self.parser.write(fileobj)
        finally:
            fileobj.close()

    def check(self, section):
        """
        Check if the config file has valid values
        """
        if not self.parser.has_section(section):
            return False, "Section not found: %s" % (section)

        options = self.parser.items(section)
        for i in range(options.__len__()):
            param = options[i][0]
            aux = string.split(param, '.')

            if aux.__len__ < 2:
                return False, "Invalid parameter syntax at %s" % (param)

            if not self.check_parameter(aux[0], options[i][1]):
                return False, "Invalid value at %s" % (param)

        return True, None

    def check_parameter(self, param_type, parameter):
        """
        Check if a option has a valid value
        """
        if parameter == '' or parameter is None:
            return False
        elif param_type == "ip" and self.__isipaddress(parameter):
            return True
        elif param_type == "int" and self.__isint(parameter):
            return True
        elif param_type == "float" and self.__isfloat(parameter):
            return True
        elif param_type == "str" and self.__isstr(parameter):
            return True

        return False

    def __isipaddress(self, parameter):
        """
        Verify if the ip address is valid

        :param ip String: IP Address
        :return: True if a valid IP Address or False
        """
        octet1 = "([1-9][0-9]{,1}|1[0-9]{2}|2[0-4][0-9]|25[0-5])"
        octet = "([0-9]{1,2}|1[0-9]{2}|2[0-4][0-9]|25[0-5])"
        pattern = "^" + octet1 + "\.(" + octet + "\.){2}" + octet + "$"
        if re.match(pattern, parameter) is None:
            return False
        else:
            return True

    def __isint(self, parameter):
        try:
            int(parameter)
        except Exception, e_stack:
            return False
        return True

    def __isfloat(self, parameter):
        try:
            float(parameter)
        except Exception, e_stack:
            return False
        return True

    def __isstr(self, parameter):
        try:
            str(parameter)
        except Exception, e_stack:
            return False
        return True


def get_known_backends():
    """
    Return virtualization backends supported by avocado-vt.
    """
    # Generic means the test can run in multiple backends, such as libvirt
    # and qemu.
    known_backends = ['generic']
    known_backends += os.listdir(data_dir.BASE_BACKEND_DIR)
    return known_backends


def get_test_provider_names(backend=None):
    """
    Get the names of all test providers available in test-providers.d.

    :return: List with the names of all test providers.
    """
    provider_name_list = []
    tp_base_dir = data_dir.get_base_test_providers_dir()
    tp_local_dir = data_dir.get_test_providers_dir()
    distutils.dir_util.copy_tree(tp_base_dir, tp_local_dir)
    provider_dir = data_dir.get_test_providers_dir()
    for provider in glob.glob(os.path.join(provider_dir, '*.ini')):
        provider_name = os.path.basename(provider).split('.')[0]
        provider_info = get_test_provider_info(provider_name)
        if backend is not None:
            if backend in provider_info['backends']:
                provider_name_list.append(provider_name)
        else:
            provider_name_list.append(provider_name)
    return provider_name_list


def get_test_provider_subdirs(backend=None):
    """
    Get information of all test provider subdirs for a given backend.

    If no backend is provided, return all subdirs with tests.

    :param backend: Backend type, such as 'qemu'.
    :return: List of directories that contain tests for the given backend.
    """
    subdir_list = []
    for provider_name in get_test_provider_names():
        provider_info = get_test_provider_info(provider_name)
        backends_info = provider_info['backends']
        if backend is not None:
            if backend in backends_info:
                subdir_list.append(backends_info[backend]['path'])
        else:
            for b in backends_info:
                subdir_list.append(backends_info[b]['path'])
    return subdir_list


def get_test_provider_info(provider):
    """
    Get a dictionary with relevant test provider info, such as:

    * provider uri (git repo or filesystem location)
    * provider git repo data, such as branch, ref, pubkey
    * backends that this provider has tests for. For each backend type the
        provider has tests for, the 'path' will be also available.

    :param provider: Test provider name, such as 'io-github-autotest-qemu'.
    """
    provider_info = {}
    provider_path = os.path.join(data_dir.get_test_providers_dir(),
                                 '%s.ini' % provider)
    provider_cfg = ConfigLoader(provider_path)
    provider_info['name'] = provider
    provider_info['uri'] = provider_cfg.get('provider', 'uri')
    provider_info['branch'] = provider_cfg.get('provider', 'branch', 'master')
    provider_info['ref'] = provider_cfg.get('provider', 'ref')
    provider_info['pubkey'] = provider_cfg.get('provider', 'pubkey')
    provider_info['backends'] = {}

    for backend in get_known_backends():
        subdir = provider_cfg.get(backend, 'subdir')
        cart_cfgs = provider_cfg.get(backend, 'configs')

        backend_dic = {}
        if cart_cfgs is not None:
            # Give ability to specify few required configs separated with comma
            cart_cfgs = [x.strip() for x in cart_cfgs.split(',')]
            backend_dic.update({'cartesian_configs': cart_cfgs})

        if subdir is not None:
            if provider_info['uri'].startswith('file://'):
                src = os.path.join(provider_info['uri'][7:],
                                   subdir)
            else:
                src = os.path.join(data_dir.get_test_provider_dir(provider),
                                   subdir)
            backend_dic.update({'path': src})
            provider_info['backends'].update({backend: backend_dic})

    return provider_info


def download_test_provider(provider, update=False):
    """
    Download a test provider defined on a .ini file inside test-providers.d.

    This function will only download test providers that are in git repos.
    Local filesystems don't need this functionality.

    :param provider: Test provider name, such as 'io-github-autotest-qemu'.
    """
    provider_info = get_test_provider_info(provider)
    uri = provider_info.get('uri')
    if not uri.startswith('file://'):
        uri = provider_info.get('uri')
        branch = provider_info.get('branch')
        ref = provider_info.get('ref')
        pubkey = provider_info.get('pubkey')
        download_dst = data_dir.get_test_provider_dir(provider)
        repo_downloaded = os.path.isdir(os.path.join(download_dst, '.git'))
        original_dir = os.getcwd()
        if not repo_downloaded or update:
            download_dst = git.get_repo(uri=uri, branch=branch, commit=ref,
                                        destination_dir=download_dst)
            os.chdir(download_dst)
            try:
                process.run('git remote add origin %s' % uri)
            except process.CmdError:
                pass
            process.run('git pull origin %s' % branch)
        os.chdir(download_dst)
        process.system('git log -1')
        os.chdir(original_dir)


def download_all_test_providers(update=False):
    """
    Download all available test providers.
    """
    for provider in get_test_provider_names():
        download_test_provider(provider, update)


def get_all_assets():
    asset_data_list = []
    download_dir = data_dir.get_download_dir()
    for asset in glob.glob(os.path.join(download_dir, '*.ini')):
        asset_name = os.path.basename(asset)[:-4]
        asset_data_list.append(get_asset_info(asset_name))
    return asset_data_list


def get_file_asset(title, src_path, destination):
    if not os.path.isabs(destination):
        destination = os.path.join(data_dir.get_data_dir(), destination)

    for ext in (".xz", ".gz", ".7z", ".bz2"):
        if os.path.exists(src_path + ext):
            destination = destination + ext
            logging.debug('Found source image %s', destination)
            return {
                'url': None, 'sha1_url': None, 'destination': src_path + ext,
                'destination_uncompressed': destination,
                'uncompress_cmd': None, 'shortname': title, 'title': title,
                'downloaded': True}

    if os.path.exists(src_path):
        logging.debug('Found source image %s', destination)
        return {'url': src_path, 'sha1_url': None, 'destination': destination,
                'destination_uncompressed': None, 'uncompress_cmd': None,
                'shortname': title, 'title': title,
                'downloaded': os.path.exists(destination)}

    return None


def get_asset_info(asset):
    asset_info = {}
    asset_path = os.path.join(data_dir.get_download_dir(), '%s.ini' % asset)
    asset_cfg = ConfigLoader(asset_path)

    asset_info['url'] = asset_cfg.get(asset, 'url')
    asset_info['sha1_url'] = asset_cfg.get(asset, 'sha1_url')
    asset_info['title'] = asset_cfg.get(asset, 'title')
    destination = asset_cfg.get(asset, 'destination')
    if not os.path.isabs(destination):
        destination = os.path.join(data_dir.get_data_dir(), destination)
    asset_info['destination'] = destination
    asset_info['asset_exists'] = os.path.isfile(destination)

    # Optional fields
    d_uncompressed = asset_cfg.get(asset, 'destination_uncompressed')
    if d_uncompressed is not None and not os.path.isabs(d_uncompressed):
        d_uncompressed = os.path.join(data_dir.get_data_dir(),
                                      d_uncompressed)
    asset_info['destination_uncompressed'] = d_uncompressed
    asset_info['uncompress_cmd'] = asset_cfg.get(asset, 'uncompress_cmd')

    return asset_info


def uncompress_asset(asset_info, force=False):
    destination = asset_info['destination']
    uncompress_cmd = asset_info['uncompress_cmd']
    destination_uncompressed = asset_info['destination_uncompressed']

    archive_re = re.compile(r".*\.(gz|xz|7z|bz2)$")
    if destination_uncompressed is not None:
        if uncompress_cmd is None:
            match = archive_re.match(destination)
            if match:
                if match.group(1) == 'gz':
                    uncompress_cmd = ('gzip -cd %s > %s' %
                                      (destination, destination_uncompressed))
                elif match.group(1) == 'xz':
                    uncompress_cmd = ('xz -cd %s > %s' %
                                      (destination, destination_uncompressed))
                elif match.group(1) == 'bz2':
                    uncompress_cmd = ('bzip2 -cd %s > %s' %
                                      (destination, destination_uncompressed))
                elif match.group(1) == '7z':
                    uncompress_cmd = '7za -y e %s' % destination
        else:
            uncompress_cmd = "%s %s" % (uncompress_cmd, destination)

    if uncompress_cmd is not None:
        uncompressed_file_exists = os.path.exists(destination_uncompressed)
        force = (force or not uncompressed_file_exists)

        if os.path.isfile(destination) and force:
            os.chdir(os.path.dirname(destination_uncompressed))
            logging.debug('Uncompressing %s -> %s', destination,
                          destination_uncompressed)
            commands.getstatusoutput(uncompress_cmd)


def download_file(asset_info, interactive=False, force=False):
    """
    Verifies if file that can be find on url is on destination with right hash.

    This function will verify the SHA1 hash of the file. If the file
    appears to be missing or corrupted, let the user know.

    :param asset_info: Dictionary returned by get_asset_info
    """
    file_ok = False
    problems_ignored = False
    had_to_download = False
    sha1 = None

    url = asset_info['url']
    sha1_url = asset_info['sha1_url']
    destination = asset_info['destination']
    title = asset_info['title']

    if sha1_url is not None:
        try:
            logging.info("Verifying expected SHA1 sum from %s", sha1_url)
            sha1_file = urllib2.urlopen(sha1_url)
            sha1_contents = sha1_file.read()
            sha1 = sha1_contents.split(" ")[0]
            logging.info("Expected SHA1 sum: %s", sha1)
        except Exception, e:
            logging.error("Failed to get SHA1 from file: %s", e)
    else:
        sha1 = None

    destination_dir = os.path.dirname(destination)
    if not os.path.isdir(destination_dir):
        os.makedirs(destination_dir)

    if not os.path.isfile(destination):
        logging.warning("File %s not found", destination)
        if interactive:
            answer = genio.ask("Would you like to download it from %s?" % url)
        else:
            answer = 'y'
        if answer == 'y':
            download.url_download_interactive(url, destination,
                                              "Downloading %s" % title)
            had_to_download = True
        else:
            logging.warning("Missing file %s", destination)
    else:
        logging.info("Found %s", destination)
        if sha1 is None:
            answer = 'n'
        else:
            answer = 'y'

        if answer == 'y':
            actual_sha1 = crypto.hash_file(destination, algorithm='sha1')
            if actual_sha1 != sha1:
                logging.info("Actual SHA1 sum: %s", actual_sha1)
                if interactive:
                    answer = genio.ask("The file seems corrupted or outdated. "
                                       "Would you like to download it?")
                else:
                    logging.info("The file seems corrupted or outdated")
                    answer = 'y'
                if answer == 'y':
                    logging.info("Updating image to the latest available...")
                    while not file_ok:
                        download.url_download_interactive(url, destination,
                                                          title)
                        sha1_post_download = crypto.hash_file(destination,
                                                              algorithm='sha1')
                        had_to_download = True
                        if sha1_post_download != sha1:
                            logging.error("Actual SHA1 sum: %s", actual_sha1)
                            if interactive:
                                answer = genio.ask("The file downloaded %s is "
                                                   "corrupted. Would you like "
                                                   "to try again?" %
                                                   destination)
                            else:
                                answer = 'n'
                            if answer == 'n':
                                problems_ignored = True
                                logging.error("File %s is corrupted" %
                                              destination)
                                file_ok = True
                            else:
                                file_ok = False
                        else:
                            file_ok = True
            else:
                file_ok = True
                logging.info("SHA1 sum check OK")
        else:
            problems_ignored = True
            logging.info("File %s present, but did not verify integrity",
                         destination)

    if file_ok:
        if not problems_ignored:
            logging.info("%s present, with proper checksum", destination)

    uncompress_asset(asset_info=asset_info, force=force or had_to_download)


def download_asset(asset, interactive=True, restore_image=False):
    """
    Download an asset defined on an asset file.

    Asset files are located under /shared/downloads, are .ini files with the
    following keys defined:

    title
        Title string to display in the download progress bar.
    url
        URL of the resource
    sha1_url
        URL with SHA1 information for the resource, in the form
        sha1sum file_basename
    destination
        Location of your file relative to the data directory
        (TEST_SUITE_ROOT/shared/data)
    destination
        Location of the uncompressed file relative to the data
        directory (TEST_SUITE_ROOT/shared/data)
    uncompress_cmd
        Command that needs to be executed with the compressed
        file as a parameter

    :param asset: String describing an asset file.
    :param interactive: Whether to ask the user before downloading the file.
    :param restore_image: If the asset is a compressed image, we can uncompress
                          in order to restore the image.
    """
    asset_info = get_asset_info(asset)
    destination = asset_info['destination']

    if (interactive and not os.path.isfile(destination)):
        answer = genio.ask("File %s not present. Do you want to download it?" %
                           asset_info['title'])
    else:
        answer = "y"

    if answer == "y":
        download_file(asset_info=asset_info, interactive=interactive,
                      force=restore_image)
