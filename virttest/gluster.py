"""
GlusterFS Support
This file has the functions that helps
* To create/check gluster volume.
* To start/check gluster services.
* To create gluster uri which can be used as disk image file path.
"""

import logging
import os
import re
import socket

from avocado.utils import process

from virttest import data_dir
from virttest import utils_misc
from virttest import utils_net
from virttest import error_context
from virttest.compat_52lts import decode_to_text


class GlusterError(Exception):
    pass


class GlusterBrickError(GlusterError):

    def __init__(self, error_mgs):
        super(GlusterBrickError, self).__init__(error_mgs)
        self.error_mgs = error_mgs

    def __str__(self):
        return "Gluster: %s" % (self.error_mgs)


@error_context.context_aware
def glusterd_start():
    """
    Check for glusterd status and start it
    """
    cmd = "service glusterd status"
    output = decode_to_text(process.system_output(cmd, ignore_status=True))
    # The blank before 'active' makes a distinction with 'inactive'
    if ' active' not in output or 'running' not in output:
        cmd = "service glusterd start"
        error_context.context("Starting gluster dameon failed")
        output = decode_to_text(process.system_output(cmd))


@error_context.context_aware
def is_gluster_vol_started(vol_name, session=None):
    """
    Return true if the volume is started, if not send false

    :param vol_name: name of gluster volume
    :param session: ShellSession object of remote host
    """
    cmd = "gluster volume info %s" % vol_name
    error_context.context(
        "Gluster volume info failed for volume: %s" % vol_name)
    if session:
        vol_info = session.cmd_output(cmd)
    else:
        vol_info = decode_to_text(process.system_output(cmd))
    volume_status = re.findall(r'Status: (\S+)', vol_info)
    if 'Started' in volume_status:
        return True
    else:
        return False


@error_context.context_aware
def gluster_vol_start(vol_name, session=None):
    """
    Start the volume if it is stopped

    :param vol_name: name of gluster volume
    :param session: ShellSession object of remote host
    """
    # Check if the volume is stopped, if then start
    if not is_gluster_vol_started(vol_name, session):
        error_context.context(
            "Gluster volume start failed for volume; %s" % vol_name)
        cmd = "gluster volume start %s" % vol_name
        if session:
            session.cmd(cmd)
        else:
            process.system(cmd)
        return True
    else:
        return True


@error_context.context_aware
def gluster_vol_stop(vol_name, force=False, session=None):
    """
    Stop the volume if it is started

    :param vol_name: volume name
    :param force: Boolean for adding force option or not
    :param session: ShellSession object of remote host
    """
    # Check if the volume is started, if then stop
    if is_gluster_vol_started(vol_name, session):
        error_context.context("Gluster volume stop for volume; %s" % vol_name)
        if force:
            cmd = "echo 'y' | gluster volume stop %s force" % vol_name
        else:
            cmd = "echo 'y' | gluster volume stop %s" % vol_name
        if session:
            session.cmd(cmd)
        else:
            process.run(cmd, ignore_status=False, shell=True)
        return True
    else:
        return True


@error_context.context_aware
def gluster_vol_delete(vol_name, session=None):
    """
    Delete the volume if it is not started

    :param vol_name: name of gluster volume
    :param session: ShellSession object of remote host
    """
    # Check if the volume is stopped, if then delete
    if not is_gluster_vol_started(vol_name, session):
        error_context.context("Gluster volume delete; %s" % vol_name)
        cmd = "echo 'y' | gluster volume delete %s" % vol_name
        if session:
            session.cmd(cmd)
        else:
            process.run(cmd, ignore_status=False, shell=True)
        return True
    else:
        return False


@error_context.context_aware
def is_gluster_vol_avail(vol_name, session=None):
    """
    Check if the volume already available

    :param vol_name: name of gluster volume
    :param session: ShellSession object of remote host
    """
    cmd = "gluster volume info"
    error_context.context("Gluster volume info failed")
    if session:
        output = session.cmd_output(cmd)
    else:
        output = decode_to_text(process.system_output(cmd))
    volume_name = re.findall(r'Volume Name: (%s)\n' % vol_name, output)
    if volume_name:
        return gluster_vol_start(vol_name, session)


def gluster_brick_create(brick_path, force=False, session=None):
    """
    Creates brick

    :param brick_path: path of gluster brick
    :param force: Boolean for force delete brick or not
    :param session: ShellSession object of remote host
    """
    if session:
        cmd1_str = "session.cmd_status('[ ! -d %s ]' % brick_path)"
        cmd2_str = "session.cmd('mkdir -p %s' % brick_path)"
    else:
        cmd1_str = "os.path.isdir(brick_path)"
        cmd2_str = "os.mkdir(brick_path)"

    if eval(cmd1_str) and force:
        gluster_brick_delete(brick_path, session)
    try:
        eval(cmd2_str)
        return True
    except OSError as details:
        logging.error("Not able to create brick folder %s", details)


def gluster_brick_delete(brick_path, session=None):
    """
    Creates brick

    :param brick_path: path of gluster brick
    :param session: ShellSession object of remote host
    """
    cmd2 = 'rm -rf %s' % brick_path
    if session:
        cmd1_str = "session.cmd_status('[ ! -d %s ]' % brick_path)"
        cmd2_str = "session.cmd(cmd2)"
    else:
        cmd1_str = "os.path.isdir(brick_path)"
        cmd2_str = "process.run(cmd2, ignore_status=False, shell=True)"

    if eval(cmd1_str):
        try:
            eval(cmd2_str)
            return True
        except OSError as details:
            logging.error("Not able to delete brick folder %s", details)


@error_context.context_aware
def gluster_vol_create(vol_name, hostname, brick_path, force=False, session=None):
    """
    Gluster Volume Creation

    :param vol_name: Name of gluster volume
    :param hostname: hostname to create gluster volume
    :param force: Boolean for adding force option or not
    """
    # Create a brick
    if is_gluster_vol_avail(vol_name, session):
        gluster_vol_stop(vol_name, True, session)
        gluster_vol_delete(vol_name, session)
        gluster_brick_delete(brick_path, session)

    gluster_brick_create(brick_path, session=session)

    if force:
        force_opt = "force"
    else:
        force_opt = ""

    cmd = "gluster volume create %s %s:/%s %s" % (vol_name, hostname,
                                                  brick_path, force_opt)
    error_context.context("Volume creation failed")
    if session:
        session.cmd(cmd)
    else:
        process.system(cmd)
    return is_gluster_vol_avail(vol_name, session)


def glusterfs_mount(g_uri, mount_point):
    """
    Mount gluster volume to mountpoint.

    :param g_uri: stripped gluster uri from create_gluster_uri(.., True)
    :type g_uri: str
    """
    utils_misc.mount(g_uri, mount_point, "glusterfs", None,
                     False, "fuse.glusterfs")


@error_context.context_aware
def create_gluster_vol(params):
    vol_name = params.get("gluster_volume_name")
    force = params.get('force_recreate_gluster') == "yes"

    brick_path = params.get("gluster_brick")
    if not os.path.isabs(brick_path):  # do nothing when path is absolute
        base_dir = params.get("images_base_dir", data_dir.get_data_dir())
        brick_path = os.path.join(base_dir, brick_path)

    error_context.context("Host name lookup failed")
    hostname = socket.gethostname()
    if not hostname or hostname == "(none)":
        if_up = utils_net.get_net_if(state="UP")
        for i in if_up:
            ipv4_value = utils_net.get_net_if_addrs(i)["ipv4"]
            logging.debug("ipv4_value is %s", ipv4_value)
            if ipv4_value != []:
                ip_addr = ipv4_value[0]
                break
        hostname = ip_addr

    # Start the gluster dameon, if not started
    glusterd_start()
    # Check for the volume is already present, if not create one.
    if not is_gluster_vol_avail(vol_name) or force:
        return gluster_vol_create(vol_name, hostname, brick_path, force)
    else:
        return True


@error_context.context_aware
def create_gluster_uri(params, stripped=False):
    """
    Find/create gluster volume
    """
    vol_name = params.get("gluster_volume_name")

    error_context.context("Host name lookup failed")
    hostname = socket.gethostname()
    gluster_server = params.get("gluster_server")
    gluster_port = params.get("gluster_port", "0")
    if not gluster_server:
        gluster_server = hostname
    if not gluster_server or gluster_server == "(none)":
        if_up = utils_net.get_net_if(state="UP")
        ip_addr = utils_net.get_net_if_addrs(if_up[0])["ipv4"][0]
        gluster_server = ip_addr

    # Start the gluster dameon, if not started
    # Building gluster uri
    gluster_uri = None
    if stripped:
        gluster_uri = "%s:/%s" % (gluster_server, vol_name)
    else:
        gluster_uri = "gluster://%s:%s/%s/" % (gluster_server, gluster_port,
                                               vol_name)
    return gluster_uri


def file_exists(params, filename_path):
    sg_uri = create_gluster_uri(params, stripped=True)
    g_uri = create_gluster_uri(params, stripped=False)
    # Using directly /tmp dir because directory should be really temporary and
    # should be deleted immediately when no longer needed and
    # created directory don't file tmp dir by any data.
    tmpdir = "gmount-%s" % (utils_misc.generate_random_string(6))
    tmpdir_path = os.path.join(data_dir.get_tmp_dir(), tmpdir)
    while os.path.exists(tmpdir_path):
        tmpdir = "gmount-%s" % (utils_misc.generate_random_string(6))
        tmpdir_path = os.path.join(data_dir.get_tmp_dir(), tmpdir)
    ret = False
    try:
        try:
            os.mkdir(tmpdir_path)
            glusterfs_mount(sg_uri, tmpdir_path)
            mount_filename_path = os.path.join(tmpdir_path,
                                               filename_path[len(g_uri):])
            if os.path.exists(mount_filename_path):
                ret = True
        except Exception as e:
            logging.error("Failed to mount gluster volume %s to"
                          " mount dir %s: %s" % (sg_uri, tmpdir_path, e))
    finally:
        if utils_misc.umount(sg_uri, tmpdir_path, "glusterfs", False,
                             "fuse.glusterfs"):
            try:
                os.rmdir(tmpdir_path)
            except OSError:
                pass
        else:
            logging.warning("Unable to unmount tmp directory %s with glusterfs"
                            " mount.", tmpdir_path)
    return ret


def get_image_filename(params, image_name, image_format):
    """
    Form the image file name using gluster uri
    """

    img_name = image_name.split('/')[-1]
    gluster_uri = create_gluster_uri(params)
    if params.get("image_raw_device") == "yes":
        image_filename = "%s%s" % (gluster_uri, img_name)
    else:
        image_filename = "%s%s.%s" % (gluster_uri, img_name, image_format)
    return image_filename


@error_context.context_aware
def gluster_allow_insecure(vol_name, session=None):
    """
    Allow gluster volume insecure

    :param vol_name: name of gluster volume
    :param session: ShellSession object of remote host
    """

    cmd1 = "gluster volume set %s server.allow-insecure on" % vol_name
    cmd2 = "gluster volume info"
    error_context.context("Volume set server.allow-insecure failed")

    if session:
        session.cmd(cmd1)
        output = session.cmd_output(cmd2)
    else:
        process.system(cmd1)
        output = decode_to_text(process.system_output(cmd2))

    match = re.findall(r'server.allow-insecure: on', output)

    if not match:
        return False
    else:
        return True


def add_rpc_insecure(filepath):
    """
    Allow glusterd RPC authority insecure
    """

    cmd = "cat %s" % filepath
    content = decode_to_text(process.system_output(cmd))
    match = re.findall(r'rpc-auth-allow-insecure on', content)
    logging.info("match is %s", match)
    if not match:
        logging.info("not match")
        cmd = "sed -i '/end-volume/i \ \ \ \ option rpc-auth-allow-insecure on' %s" % filepath
        process.system(cmd, shell=True)
        process.system("service glusterd restart; sleep 2", shell=True)


@error_context.context_aware
def gluster_nfs_disable(vol_name, session=None):
    """
    Turn-off export of volume through NFS

    :param vol_name: name of gluster volume
    :param session: Shell session for remote execution
    """

    cmd1 = "gluster volume set %s nfs.disable on" % vol_name
    cmd2 = "gluster volume info %s" % vol_name
    error_context.context("Volume set nfs.disable failed")

    if session:
        session.cmd(cmd1)
        output = session.cmd_output(cmd2)
    else:
        process.system(cmd1)
        output = decode_to_text(process.system_output(cmd2))

    return 'nfs.disable: on' in output
