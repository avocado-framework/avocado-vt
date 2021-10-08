import os
import logging

import aexpect
from aexpect import remote

from avocado.utils import process
from avocado.utils import path

from virttest import remote as remote_old

LOG = logging.getLogger('avocado.' + __name__)


def get_public_key(client_user=None):
    """
    Return a valid string ssh public key for the user executing autoserv or
    autotest. If there's no DSA or RSA public key, create a RSA keypair with
    ssh-keygen and return it.

    :param client_user: genenrate the ssh_key for which client
                        user to login into the server
    :type client_user: str
    :returns: a ssh public key
    :rtype: str
    """

    if client_user:
        if os.environ.get('USER') not in ('root', client_user):
            raise RuntimeError("Can not set ssh-key for OTHER user using"
                               "non-root account. Permission Denied.")
        if client_user == 'root':
            ssh_conf_path = '/root/.ssh'
        else:
            ssh_conf_path = '/home/%s/.ssh' % client_user
    else:
        ssh_conf_path = os.path.expanduser('~/.ssh')
        client_user = os.environ.get('USER')

    dsa_public_key_path = os.path.join(ssh_conf_path, 'id_dsa.pub')
    dsa_private_key_path = os.path.join(ssh_conf_path, 'id_dsa')

    rsa_public_key_path = os.path.join(ssh_conf_path, 'id_rsa.pub')
    rsa_private_key_path = os.path.join(ssh_conf_path, 'id_rsa')

    has_dsa_keypair = (os.path.isfile(dsa_public_key_path) and
                       os.path.isfile(dsa_private_key_path))
    has_rsa_keypair = (os.path.isfile(rsa_public_key_path) and
                       os.path.isfile(rsa_private_key_path))

    if has_rsa_keypair:
        LOG.info('RSA keypair found, using it')
        public_key_path = rsa_public_key_path

    elif has_dsa_keypair:
        LOG.info('DSA keypair found, using it')
        public_key_path = dsa_public_key_path

    else:
        LOG.info('Neither RSA nor DSA keypair found, creating RSA ssh key pair')
        if os.environ.get('USER') != 'root':
            process.system('ssh-keygen -t rsa -q -N \"\" -f %s' %
                           rsa_private_key_path, shell=True)
        else:
            process.system("su - %s -c 'ssh-keygen -t rsa -q -N \"\" -f %s'" %
                           (client_user, rsa_private_key_path), shell=True)
        public_key_path = rsa_public_key_path

    public_key = open(public_key_path, 'r')
    public_key_str = public_key.read()
    public_key.close()

    return public_key_str


def get_remote_public_key(session, public_key="rsa"):
    """
    Return a valid string ssh public key for the user executing autoserv or
    autotest. If there's no DSA or RSA public key, create a RSA keypair with
    ssh-keygen and return it.

    :param session: A ShellSession for remote host
    :returns: a ssh public key
    :rtype: str
    """
    session.cmd_output("mkdir -p ~/.ssh")
    session.cmd_output("chmod 700 ~/.ssh")

    ssh_conf_path = "~/.ssh"
    dsa_public_key_path = os.path.join(ssh_conf_path, 'id_dsa.pub')
    dsa_private_key_path = os.path.join(ssh_conf_path, 'id_dsa')

    rsa_public_key_path = os.path.join(ssh_conf_path, 'id_rsa.pub')
    rsa_private_key_path = os.path.join(ssh_conf_path, 'id_rsa')

    dsa_public_s = session.cmd_status("ls %s" % dsa_public_key_path)
    dsa_private_s = session.cmd_status("ls %s" % dsa_private_key_path)
    rsa_public_s = session.cmd_status("ls %s" % rsa_public_key_path)
    rsa_private_s = session.cmd_status("ls %s" % rsa_private_key_path)

    has_dsa_keypair = dsa_public_s == 0 and dsa_private_s == 0
    has_rsa_keypair = rsa_public_s == 0 and rsa_private_s == 0

    if has_dsa_keypair and public_key == "dsa":
        LOG.info('DSA keypair found on %s, using it', session)
        public_key_path = dsa_public_key_path

    elif has_rsa_keypair and public_key == "rsa":
        LOG.info('RSA keypair found on %s, using it', session)
        public_key_path = rsa_public_key_path

    else:
        LOG.info('Neither RSA nor DSA keypair found, '
                 'creating %s ssh key pair' % public_key)
        key_path = rsa_private_key_path
        public_key_path = rsa_public_key_path
        if public_key == "dsa":
            key_path = dsa_private_key_path
            public_key_path = dsa_public_key_path
        session.cmd('ssh-keygen -t %s -q -N "" -f %s' %
                    (public_key, key_path))

    return session.cmd_output("cat %s" % public_key_path)


def setup_ssh_key(hostname, user, password, port=22, client_user=None):
    """
    Setup up remote login in another server by using public key

    :param hostname: the server to login
    :type hostname: str
    :param user: user to login
    :type user: str
    :param password: password
    :type password: str
    :param port: port number
    :type port: int
    :param client_user: genenrate the ssh_key for which client
                        user to login into the server
    :type client_user: str
    """
    LOG.debug('Performing SSH key setup on %s:%d as %s.' %
              (hostname, port, user))

    try:
        session = remote.remote_login(client='ssh', host=hostname,
                                      username=user, port=port,
                                      password=password, prompt=r'[$#%]')
        public_key = get_public_key(client_user)

        session.cmd('mkdir -p ~/.ssh')
        session.cmd('chmod 700 ~/.ssh')
        session.cmd("echo '%s' >> ~/.ssh/authorized_keys; " %
                    public_key)
        session.cmd('chmod 600 ~/.ssh/authorized_keys')
        LOG.debug('SSH key setup complete.')

    except Exception:
        LOG.debug('SSH key setup has failed.')

    finally:
        try:
            session.close()
        except Exception:
            pass


def setup_remote_ssh_key(hostname1, user1, password1,
                         hostname2=None, user2=None, password2=None,
                         port=22, config_options=None, public_key="rsa"):
    """
    Setup up remote to remote login in another server by using public key
    If hostname2 is not supplied, setup to local.

    :param hostname1: the server wants to login other host
    :param hostname2: the server to be logged in
    :type hostname: str
    :param user: user to login
    :type user: str
    :param password: password
    :type password: str
    :param port: port number
    :type port: int
    :param config_options: list of options eg: ["StrictHostKeyChecking=no"]
    :type config_options: list of str
    """
    LOG.debug('Performing SSH key setup on %s:%d as %s.' %
              (hostname1, port, user1))

    try:
        session1 = remote.remote_login(client='ssh', host=hostname1, port=port,
                                       username=user1, password=password1,
                                       prompt=r'[$#%]')
        public_key = get_remote_public_key(session1, public_key=public_key)

        if hostname2 is None:
            # Simply create a session to local
            session2 = aexpect.ShellSession("sh", linesep='\n', prompt='#')
            # set config in local machine
            if config_options:
                for each_option in config_options:
                    session2.cmd_output("echo '%s' >> ~/.ssh/config" %
                                        each_option)
        else:
            session2 = remote.remote_login(client='ssh', host=hostname2,
                                           port=port, username=user2,
                                           password=password2,
                                           prompt=r'[$#%]')
            # set config in remote machine
            if config_options:
                for each_option in config_options:
                    session1.cmd_output("echo '%s' >> ~/.ssh/config" %
                                        each_option)
        session2.cmd_output('mkdir -p ~/.ssh')
        session2.cmd_output('chmod 700 ~/.ssh')
        session2.cmd_output("echo '%s' >> ~/.ssh/authorized_keys; " %
                            public_key)
        session2.cmd_output('chmod 600 ~/.ssh/authorized_keys')
        LOG.debug('SSH key setup on %s complete.', session2)
    except Exception as err:
        LOG.debug('SSH key setup has failed: %s', err)
        try:
            session1.close()
            session2.close()
        except Exception:
            pass


def setup_remote_known_hosts_file(client_ip, server_ip,
                                  server_user, server_pwd):
    """
    Set the ssh host key of local host to remote host

    :param client_ip: local host ip whose host key is sent to remote host
    :type client_ip: str
    :param server_ip: remote host ip address where host key is stored to
    :type server_ip: str
    :param server_user: user to log on remote host
    :type server_user: str
    :param server_pwd: password for the user for log on remote host
    :type server_pwd: str

    :return: a RemoteFile object for the file known_hosts on remote host
    :rtype: remote_old.RemoteFile
    :return: None if required command is not found
    """
    LOG.debug('Performing known_hosts file setup on %s from %s.' %
              (server_ip, client_ip))
    abs_path = ""
    try:
        abs_path = path.find_command("ssh-keyscan")
    except path.CmdNotFoundError as err:
        LOG.debug("Failed to find the command: %s", err)
        return None

    cmd = "%s %s" % (abs_path, client_ip)
    host_key = process.run(cmd, verbose=False).stdout_text
    remote_known_hosts_file = remote_old.RemoteFile(
        address=server_ip,
        client='scp',
        username=server_user,
        password=server_pwd,
        port='22',
        remote_path='~/.ssh/known_hosts')
    pattern2repl = {r".*%s[, ].*" % client_ip: host_key}
    remote_known_hosts_file.sub_else_add(pattern2repl)
    return remote_known_hosts_file
