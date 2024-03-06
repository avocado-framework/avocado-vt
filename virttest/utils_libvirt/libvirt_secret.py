"""
Secret related utility functions
"""

import logging
import re

from aexpect import remote
from avocado.core import exceptions

from virttest import virsh
from virttest.libvirt_xml import secret_xml
from virttest.utils_test import libvirt

LOG = logging.getLogger("avocado." + __name__)


def create_secret(sec_dict, remote_args=None):
    """
    Create a secret with 'virsh secret-define'

    :param sec_dict: dict to create secret
    :param remote_args: Parameters for remote host
    :return: UUID of the secret

    Example:

        secret_dict = {'secret_ephemeral': 'no',
                    'secret_private': 'yes',
                    'description': 'secret desc',
                    'usage': 'volume',
                    'volume': '/path/to/volume'}
        sec_uuid = libvirt_secret.create_secret(sec_dict=secret_dict)
    """

    sec_xml = secret_xml.SecretXML()
    sec_xml.setup_attrs(**sec_dict)
    sec_xml.xmltreefile.write()

    # define the secret and get its uuid
    if remote_args:
        server_ip = remote_args.get("remote_ip", "")
        server_user = remote_args.get("remote_user", "")
        server_pwd = remote_args.get("remote_pwd", "")
        if not all([server_ip, server_user, server_pwd]):
            raise exceptions.TestError("remote_[ip|user|pwd] are necessary!")
        remote_virsh_session = virsh.VirshPersistent(**remote_args)
        remote.scp_to_remote(
            server_ip,
            "22",
            server_user,
            server_pwd,
            sec_xml.xml,
            sec_xml.xml,
            limit="",
            log_filename=None,
            timeout=600,
            interface=None,
        )
        ret = remote_virsh_session.secret_define(sec_xml.xml)
        remote_virsh_session.close_session()
    else:
        ret = virsh.secret_define(sec_xml.xml)
        libvirt.check_exit_status(ret)
    try:
        sec_uuid = re.findall(r".+\S+(\ +\S+)\ +.+\S+", ret.stdout_text)[0].lstrip()
    except IndexError:
        raise exceptions.TestError("Fail to get newly created secret uuid")

    return sec_uuid


def get_secret_list(remote_virsh=None):
    """
    Get secret list by virsh secret-list from local or remote host.

    :param remote_virsh: remote virsh shell session.
    :return secret list including secret UUID
    """
    LOG.info("Get secret list ...")
    try:
        if remote_virsh:
            secret_list_result = remote_virsh.secret_list()
        else:
            secret_list_result = virsh.secret_list()
    except Exception as e:
        LOG.error("Exception thrown while getting secret lists: %s", str(e))
        raise
    secret_list = secret_list_result.stdout_text.strip().splitlines()
    # First two lines contain table header followed by entries
    # for each secret, such as:
    #
    # UUID                                  Usage
    # --------------------------------------------------------------------------------
    # b4e8f6d3-100c-4e71-9f91-069f89742273  ceph client.libvirt secret
    secret_list = secret_list[2:]
    result = []
    # If secret list is empty.
    if secret_list:
        for line in secret_list:
            # Split on whitespace, assume 1 column
            linesplit = line.split(None, 1)
            result.append(linesplit[0])
    return result


def clean_up_secrets(remote_virsh=None):
    """
    Clean up secrets

    :param remote_virsh: remote virsh shell session.
    """
    secret_list = get_secret_list(remote_virsh)
    if secret_list:
        for secret_uuid in secret_list:
            try:
                if remote_virsh:
                    remote_virsh.secret_undefine(secret_uuid)
                else:
                    virsh.secret_undefine(secret_uuid)
            except Exception as e:
                LOG.error("Exception thrown while undefining secret: %s", str(e))
                raise
