import os
import string

from virttest import error_context
from virttest import utils_misc

from avocado.utils import process


@error_context.context_aware
def get_image_filename(params):
    """
    Get the nbd image uri:
      tcp: nbd://<server-ip>[:<port>]/[<export>]
      unix domain socket: nbd+unix:///[<export>]?socket=<domain-socket>
    :param params: image specified params
    :return: nbd image uri string
    """
    server = params.get('nbd_server')
    unix_socket = params.get('nbd_unix_socket')
    export_name = '/%s' % params['nbd_export_name'] if params.get(
        'nbd_export_name') else ''

    if server:
        port = ':%s' % params['nbd_port'] if params.get('nbd_port') else ''
        return 'nbd://{server}{port}{export}'.format(server=server,
                                                     port=port,
                                                     export=export_name)
    elif unix_socket:
        return 'nbd+unix://{export}?socket={sock}'.format(export=export_name,
                                                          sock=unix_socket)

    raise ValueError('Either nbd_server or nbd_unix_socket is required.')


@error_context.context_aware
def export_image(qemu_nbd, filename, local_image, params):
    """
    Export a local file image with qemu-nbd command
    :param qemu_nbd: path to the qemu-nbd binary
    :param filename: image path for raw/qcow2 image or image json
                     representation string for luks image
    :param local_image: image tag defined in parameter images
    :param params: local image specified params
    :return: pid of qemu-nbd server or None
    """
    cmd_dict = {
        "secret_object": "",
        "tls_creds": "",
        "export_format": "",
        "persistent": "-t",
        "desc": "",
        "port": "",
        "export_name": "",
        "unix_socket": "",
        "filename": "",
        "fork": "--fork",
        "pid_file": "",
        "bitmap": ""
    }
    export_cmd = ('{secret_object} {tls_creds} '
                  '{export_format} {persistent} {desc} {port} {bitmap} '
                  '{export_name} {fork} {pid_file} {unix_socket} {filename}')

    pid_file = utils_misc.generate_tmp_file_name('%s_nbd_server' % local_image,
                                                 'pid')
    cmd_dict['pid_file'] = '--pid-file %s' % pid_file
    cmd_dict['filename'] = filename

    # auto-detect format if format(-f) is not specified
    if params.get('nbd_export_format'):
        cmd_dict['export_format'] = '-f %s' % params['nbd_export_format']

        if params['nbd_export_format'] == 'luks':
            # We can only export a local luks image in luks
            if params.get("image_format") != 'luks':
                raise ValueError("Only a luks image can be exported in luks")

            secret_str = '--object secret,id={aid},data={data}'
            cmd_dict.update({
                'secret_object': secret_str.format(
                    aid='%s_encrypt0' % local_image,
                    data=params["image_secret"]),
                'filename': "'%s'" % filename
            })

    if params.get('nbd_export_name'):
        cmd_dict['export_name'] = '-x %s' % params['nbd_export_name']

    if params.get('nbd_export_description'):
        cmd_dict['desc'] = '-D "%s"' % params['nbd_export_description']

    if params.get('nbd_unix_socket'):
        cmd_dict['unix_socket'] = '-k %s' % params['nbd_unix_socket']
    else:
        # 10809 is used by defalut if port is not set
        if params.get('nbd_port'):
            cmd_dict['port'] = '-p %s' % params['nbd_port']

        # tls creds is supported for ip only
        if params.get('nbd_server_tls_creds'):
            tls_str = ('--object tls-creds-x509,id={aid},endpoint=server,'
                       'dir={tls_creds} --tls-creds {aid}')
            cmd_dict['tls_creds'] = tls_str.format(
                aid='%s_server_tls_creds' % local_image,
                tls_creds=params['nbd_server_tls_creds']
            )

    if params.get('nbd_export_bitmap'):
        cmd_dict['bitmap'] = '-B %s' % params['nbd_export_bitmap']

    qemu_nbd_pid = None
    cmdline = qemu_nbd + ' ' + string.Formatter().format(export_cmd,
                                                         **cmd_dict)
    result = process.run(cmdline, ignore_status=True, shell=True,
                         ignore_bg_processes=True)
    if result.exit_status == 0:
        with open(pid_file, "r") as pid_file_fd:
            qemu_nbd_pid = int(pid_file_fd.read().strip())
        os.unlink(pid_file)

    return qemu_nbd_pid


def list_exported_image(qemu_nbd, nbd_image, params):
    """
    List all details about the exports by qemu-nbd
    :param qemu_nbd: path to the qemu-nbd binary
    :param nbd_image: nbd image tag defined in parameter images
    :param params: nbd image specified params
    :return: CmdResult object of qemu-nbd output
    """
    cmd_dict = {
        "tls_creds": "",
        "port": "",
        "server": ""
    }
    list_cmd = '-L {tls_creds} {port} {server}'

    if params.get('nbd_unix_socket'):
        cmd_dict['server'] = '-k %s' % params['nbd_unix_socket']
    else:
        # 0.0.0.0 is used by default if interface is not set
        if params.get('nbd_server'):
            cmd_dict['server'] = '-b %s' % params['nbd_server']

        # 10809 is used by default if port is not set
        if params.get('nbd_port'):
            cmd_dict['port'] = '-p %s' % params['nbd_port']

        # tls creds is supported for ip only
        if params.get('nbd_client_tls_creds'):
            tls_str = ('--object tls-creds-x509,id={aid},endpoint=client,'
                       'dir={tls_creds} --tls-creds {aid}')
            cmd_dict['tls_creds'] = tls_str.format(
                aid='%s_client_tls_creds' % nbd_image,
                tls_creds=params['nbd_client_tls_creds']
            )

    cmdline = qemu_nbd + ' ' + string.Formatter().format(list_cmd,
                                                         **cmd_dict)
    return process.run(cmdline, ignore_status=True, shell=True,
                       ignore_bg_processes=True)
