"""
Secret related utility functions
"""

import logging

from virttest import virsh


def get_secret_list(remote_virsh=None):
    """
    Get secret list by virsh secret-list from local or remote host.

    :param remote_virsh: remote virsh shell session.
    :return secret list including secret UUID
    """
    logging.info("Get secret list ...")
    try:
        if remote_virsh:
            secret_list_result = remote_virsh.secret_list()
        else:
            secret_list_result = virsh.secret_list()
    except Exception as e:
        logging.error("Exception thrown while getting secret lists: %s", str(e))
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
                logging.error("Exception thrown while undefining secret: %s", str(e))
                raise
