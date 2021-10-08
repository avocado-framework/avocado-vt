"""
Helpers for export one image by qemu-nbd,which can be consumed by VM.
qemu-img create -f qcow2 /tmp/disk.qcow2 1G
disk xml:
    <disk type='network' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source protocol='nbd' tls='no'>
        <host name='localhost' port='10001'/>
      </source>
      <target dev='sda' bus='scsi'/>
    </disk>
"""
import logging
import os
import shutil

from avocado.utils import process

from virttest import utils_config
from virttest import utils_libvirtd
from virttest import utils_net

from virttest.utils_conn import build_server_key, build_CA, build_client_key

LOG = logging.getLogger('avocado.' + __name__)


class NbdExport(object):
    """qemu-nbd export disk images.

    use it by referring to below steps:
    1) nbd = NbdExport("/var/lib/libvirt/images/nbd.qcow2", port=nbd_server_port, export_name=export_name, tls=tls_enabled)
    2) nbd.start_nbd_server()
       ....
    3) nbd.cleanup()
    """

    def __init__(self, image, image_format="raw", image_size="1G", port="10001", export_name=None, tls=False, deleteExisted=True,
                 private_key_encrypt_passphrase=None, secret_uuid=None):
        """Create a new NbdExport instance

        :param image: instance of image created
        :param image_format: image format,e.g raw or qcom2
        :param image_size: image size
        :param port: port where qemu-nbd export image
        :param export_name: exported alias name
        :param tls: whether use tls for encryption communication
        :param deleteExisted: whether delete currently existed image file
        :param private_key_encrypt_passphrase: password which is used to encrypt private key
        :param secret_uuid: secret id that need written into qemu.conf
        """
        # Input
        self.image = image
        self.image_format = image_format
        self.image_size = image_size
        self.port = port
        self.export_name = export_name
        self.tls = tls
        if self.tls:
            self.qemu_conf = None
            self.libvirtd = None
            self.private_key_encrypt_passphrase = private_key_encrypt_passphrase
            self.secret_uuid = secret_uuid
        self.deleteExisted = deleteExisted

    def _create_img(self):
        """Create a image file with specified format"""
        if os.path.exists(self.image):
            LOG.info('image already existed')
            if self.deleteExisted:
                os.remove(self.image)
            else:
                return
        LOG.debug("create one image .... if not existed")
        process.run("qemu-img create" + ' -f %s %s %s' % (self.image_format, self.image, self.image_size),
                    ignore_status=True, shell=True, verbose=True)

    def update_nbd_tls_config(self):
        """update nbd tls config in qemu.conf"""
        self.qemu_conf = utils_config.LibvirtQemuConfig()
        client_cert_dir = "/etc/pki/libvirt-nbd"
        self.qemu_conf.nbd_tls_x509_cert_dir = "%s" % client_cert_dir
        self.qemu_conf.nbd_tls = True
        if self.secret_uuid:
            self.qemu_conf.nbd_tls_x509_secret_uuid = "%s" % self.secret_uuid
        self.libvirtd = utils_libvirtd.Libvirtd()
        self.libvirtd.restart()

    def setup_certs(self):
        """setup CA and certs"""
        tmp_ca_cert_dir = '/etc/pki/qemu'
        # Remove old CA information.
        if os.path.exists(tmp_ca_cert_dir):
            shutil.rmtree(tmp_ca_cert_dir)

        # Get server hostname.
        hostname = process.run('hostname', ignore_status=False, shell=True, verbose=True).stdout_text.strip()
        server_ip = utils_net.get_host_ip_address()
        # Initialize the CA information.
        cn = hostname
        ca_credential_dict = {}
        ca_credential_dict['cakey'] = 'ca-key.pem'
        ca_credential_dict['cacert'] = 'ca-cert.pem'
        if not os.path.exists(tmp_ca_cert_dir):
            os.makedirs(tmp_ca_cert_dir)
        build_CA(tmp_ca_cert_dir, cn, certtool="certtool",
                 credential_dict=ca_credential_dict)

        # Create CA folder
        ca_folder = '/etc/pki/CA'
        ca_folder_private = '/etc/pki/CA/private'
        if os.path.exists(ca_folder):
            shutil.rmtree(ca_folder)
        if not os.path.exists(ca_folder):
            os.makedirs(ca_folder)
        if not os.path.exists(ca_folder_private):
            os.makedirs(ca_folder_private)
        # Copy ca-key.pem and ca-cert.pem into CA folder.
        shutil.copy2(os.path.join(tmp_ca_cert_dir, ca_credential_dict['cakey']), os.path.join(ca_folder_private, ca_credential_dict['cakey']))

        # Create server certs and keys
        server_cert_dir = '/etc/pki/qemu'
        if not os.path.exists(server_cert_dir):
            os.makedirs(server_cert_dir)
        server_credential_dict = {}
        server_credential_dict['cakey'] = 'ca-key.pem'
        server_credential_dict['cacert'] = 'ca-cert.pem'
        server_credential_dict['serverkey'] = 'server-key.pem'
        server_credential_dict['servercert'] = 'server-cert.pem'
        server_credential_dict['ca_cakey_path'] = tmp_ca_cert_dir
        # Build a server key.

        build_server_key(server_cert_dir, cn, server_ip, certtool="certtool",
                         credential_dict=server_credential_dict, on_local=True)

        server_key_path = os.path.join(server_cert_dir, server_credential_dict['serverkey'])

        # Create server certs and keys
        client_cert_dir = '/etc/pki/libvirt-nbd'
        # Clean up old client certs and keys.
        if os.path.exists(client_cert_dir):
            shutil.rmtree(client_cert_dir)
        if not os.path.exists(client_cert_dir):
            os.makedirs(client_cert_dir)
        # Copy ca-key.pem and ca-cert.pem into client_cert_dir
        shutil.copy2(os.path.join(tmp_ca_cert_dir, ca_credential_dict['cakey']), os.path.join(client_cert_dir, ca_credential_dict['cakey']))
        shutil.copy2(os.path.join(tmp_ca_cert_dir, ca_credential_dict['cacert']), os.path.join(client_cert_dir, ca_credential_dict['cacert']))
        client_credential_dict = {}
        client_credential_dict['cakey'] = 'ca-key.pem'
        client_credential_dict['cacert'] = 'ca-cert.pem'
        client_credential_dict['clientkey'] = 'client-key.pem'
        client_credential_dict['clientcert'] = 'client-cert.pem'
        if self.private_key_encrypt_passphrase:
            client_credential_dict['clientprivatekeypass'] = self.private_key_encrypt_passphrase
        server_credential_dict['ca_cakey_path'] = tmp_ca_cert_dir

        # build a client key.
        build_client_key(client_cert_dir,
                         client_cn=cn, certtool="certtool",
                         credential_dict=client_credential_dict)

    def start_nbd_server(self):
        """start nbd server"""
        # Clean up pre-occupied port if existed.
        pre_clean = "kill -9 $(ps aux | grep 'qemu-nbd'|grep %s | awk '{print $2}')" % self.port
        process.run(pre_clean, ignore_status=True, shell=True, verbose=False)
        # Create image.
        self._create_img()
        # Start qemu nbd server.
        try:
            tls_object_str = ' '
            if self.tls:
                self.setup_certs()
                self.update_nbd_tls_config()
                tls_creds = 'libivrt_%s' % self.port
                tls_object_str = "--object tls-creds-x509,id=%s,endpoint=server,dir=/etc/pki/qemu  --tls-creds=%s" % (tls_creds, tls_creds)

            qemu_nbd_cmd = 'qemu-nbd -t %s -f %s %s -p %s ' % (tls_object_str, self.image_format, self.image, self.port)
            if self.export_name:
                qemu_nbd_cmd += "-x %s " % self.export_name
            qemu_nbd_cmd += "&"
            process.run(qemu_nbd_cmd, ignore_status=False, shell=True, verbose=True, ignore_bg_processes=True)
            LOG.info("nbd server start at port: %s", self.port)
        except Exception as info:
            LOG.debug("nbd server fail to start")
            raise

    def stop_nbd_server(self):
        """stop nbd server"""
        kill_cmd = "kill -9 $(ps aux | grep 'qemu-nbd'|grep %s | awk '{print $2}')" % self.port
        process.run(kill_cmd, ignore_status=True, shell=True, verbose=False)

    def cleanTLS(self):
        """clean TLS"""
        LOG.debug("enter cleanup TLS now...")
        if self.tls:
            ca_folder = '/etc/pki/CA'
            if os.path.exists(ca_folder):
                shutil.rmtree(ca_folder)
            server_cert_dir = '/etc/pki/qemu'
            if os.path.exists(server_cert_dir):
                shutil.rmtree(server_cert_dir)
            client_cert_dir = '/etc/pki/libvirt-nbd'
            if os.path.exists(client_cert_dir):
                shutil.rmtree(client_cert_dir)
        if self.qemu_conf:
            self.qemu_conf.restore()
        if self.libvirtd:
            self.libvirtd.restart()

    def cleanup(self):
        """clean up environments"""
        self.stop_nbd_server()
        if os.path.exists(self.image) and self.deleteExisted:
            os.remove(self.image)
        if self.tls:
            self.cleanTLS()
