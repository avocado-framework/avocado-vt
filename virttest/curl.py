from virttest import error_context

from avocado.utils import process


@error_context.context_aware
def get_image_filename(curl_protocol, curl_server, curl_path,
                       curl_user=None, curl_passwd=None):
    """
    Form the url: <protocol>://[<username>[:<password>]@]<host>/<path>

    :param curl_protocol: one of 'http', 'https', 'ftp', 'ftps'
    :param curl_server: Address of the remote server
    :param curl_path: Path on the remote server, including any query string
    :param curl_user: Username for authentication to the remote server
    :param curl_passwd: Password for authentication to the remote server
    :return: Remote image filename in url format
    """
    url = "{protocol}://{auth}{host}/{path}"

    protocols = ('http', 'https', 'ftp', 'ftps')
    if curl_protocol not in protocols:
        raise ValueError('curl_protocol should be in %s.' % str(protocols))

    auth = ''
    if curl_user:
        auth = '%s:%s@' % (curl_user,
                           curl_passwd) if curl_passwd else '%s@' % curl_user

    return url.format(protocol=curl_protocol, auth=auth,
                      host=curl_server, path=curl_path)


@error_context.context_aware
def file_exists(params, filename):
    """
    Check whether the image on curl storage exists.

    :param params: A dict containing image parameters.
    :param filename: The image filename
    :return: True if the image exists, else False
    """
    curl_cmd = 'curl -I -L -k {tmo} {filename}'
    t = '-m %s' % params['curl_timeout'] if params.get('curl_timeout') else ''
    o = process.run(curl_cmd.format(tmo=t, filename=filename),
                    ignore_status=True, verbose=True).stdout_text.strip()
    return 'Content-Length:' in o
