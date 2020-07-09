from virttest import error_context

from avocado.utils import process


@error_context.context_aware
def get_image_filename(server, image_path, user=None, port=None,
                       host_key_check=None):
    """
    Form remote image filename in uri format:
    ssh://[USER@]SERVER[:PORT]/PATH[?host_key_check=HOST_KEY_CHECK]
    :param server: The remote ssh server
    :param image_path: Path to the disk image on remote server
    :param user: Remote user, ff not specified, then the local
                 username is tried
    :param port: Port number on which sshd is listening(The default is 22)
    :param host_key_check: 'yes': to use the local '.ssh/known_hosts' file,
                           the default is yes
                           'no': to turn off known-hosts checking
                           'fingerprint': to check the host key matches a
                           specific fingerprint, e.g.
                           'md5:78:45:8e:14:57:4f:d5:45:83:0a:0e:f3...',
                           note 'sha1:' can also be used as a prefix, but
                           OpenSSH only use md5 to print fingerprints
    :return: remote image filename in uri format
    """
    uri = "ssh://{user}{host}{path}{key_check}"
    user = '%s@' % user if user else ''
    host = '%s:%s' % (server, port) if port else server
    key_check = '?host_key_check=%s' % host_key_check if host_key_check else ''

    return uri.format(user=user, host=host,
                      path=image_path, key_check=key_check)


@error_context.context_aware
def file_exists(params, filename):
    """
    Check if the image exists on libssh storage backend.
    :param params: A dict containing image parameters.
    :param filename: The libssh image filename
    :return: True if the image exists, else False
    """
    ssh_cmd = ('ssh -o StrictHostKeyChecking=no -o ConnectTimeout={tmo} '
               '{port} {host} test -e {filename}')

    tmo = params.get('image_ssh_connect_timeout', '20')
    port = '-p %s' % params['image_ssh_port'] if params.get(
        'image_ssh_port') else ''
    host = '%s@%s' % (
        params['image_ssh_user'], params['image_ssh_host']
    ) if params.get('image_ssh_user') else params['image_ssh_host']

    r = process.run(ssh_cmd.format(tmo=tmo, port=port, host=host,
                                   filename=params['image_ssh_path']),
                    shell=True, verbose=True, ignore_status=True)
    return r.exit_status == 0
