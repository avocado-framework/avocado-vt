# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2023
# Authors: Zhenchao Liu <zhencliu@redhat.com>

import os
import re

from avocado.utils import process
from avocado.utils.path import find_command


# Filter out the ANSI escape sequences, e.g. if the output is colored,
# we get the ANSI escape sequences and it's hard to read, remove them
ANSI_ESCAPE_PATTERN = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
SEVCTL_BINARY = find_command('sevctl', '/usr/bin/sevctl')


def rotate_pdh():
    """
    Rotates the Platform Diffie-Hellman (PDH)

    :raise: process.CmdError
    """
    process.system(f'{SEVCTL_BINARY} rotate',
                   shell=True, verbose=False, ignore_status=False)


def reset_platform():
    """
    Resets the SEV platform, this will clear all persistent data
    managed by the platform

    :raise: process.CmdError
    """
    process.system(f'{SEVCTL_BINARY} reset',
                   shell=True, verbose=False, ignore_status=False)


def generate_oca(cert_file, key_file):
    """
    Generate a new self-signed OCA certificate and key, output to files

    :param cert_file: OCA certificate output file path
    :type cert_file: str
    :param key_file: OCA key output file path
    :type key_file: str
    :raise: process.CmdError
    """
    process.system(f'{SEVCTL_BINARY} generate {cert_file} {key_file}',
                   shell=True, verbose=False, ignore_status=False)


def provision_oca(cert_file, key_file):
    """
    Installs the operator-provided OCA certificate to
    take ownership of the platform

    :param cert_file: Path to the owner's OCA certificate file
    :type cert_file: str
    :param key_file: Path to the owner's OCA private key file
    :type key_file: str
    :raise: process.CmdError
    """
    process.system(f'{SEVCTL_BINARY} provision {cert_file} {key_file}',
                   shell=True, verbose=False, ignore_status=False)


def export_cert_chain(cert_file, full=True):
    """
    Export the SEV or entire certificate chain to a specified file

    :param cert_file: Certificate chain output file path
    :type cert_file: str
    :param full: Export the entire certificate chain(SEV + CA chain) if True,
                 or export the SEV certificate chain if False
    :type full: bool
    :raise: process.CmdError
    """
    flags = '--full' if full else ''
    process.system(f'{SEVCTL_BINARY} export {flags} {cert_file}',
                   shell=True, verbose=False, ignore_status=False)


def verify_cert_chain():
    """
    Verifies the certificate chain from the well-known public components,
    downloaded from their remote locations

    :returns: (True/False, output of verify command),
              True if the cert chain is verified successfully, else False
    :rtype: a tuple of (bool, str)
    """
    r = process.run(f'{SEVCTL_BINARY} verify',
                    shell=True, verbose=False, ignore_status=True)
    if r.exit_status == 0:
        return True, ANSI_ESCAPE_PATTERN.sub('', r.stdout_text)
    return False, ANSI_ESCAPE_PATTERN.sub('', r.stdout_text + r.stderr_text)


def verify_cert_chain_from_file(cert_type, cert_file):
    """
    Verifies the the certificate chain from a specified file

    :param cert_type: 'ca' or 'oca'or 'sev'
    :type cert_file: str
    :param cert_file: Specified certificate chain file
    :type cert_file: str
    :returns: (True/False, output of verify command),
              True if the cert chain is verified successfully, else False
    :rtype: a tuple of (bool, str)
    """
    r = process.run(f'{SEVCTL_BINARY} verify --{cert_type} {cert_file}',
                    shell=True, verbose=False, ignore_status=True)
    if r.exit_status == 0:
        return True, ANSI_ESCAPE_PATTERN.sub('', r.stdout_text)
    return False, ANSI_ESCAPE_PATTERN.sub('', r.stdout_text + r.stderr_text)


def get_platform_flags():
    """
    Display the current SEV platform flags, e.g. es

    :returns: The list of platform flag string
    :rtype: list of str
    :raise: process.CmdError
    """
    return process.run(f'{SEVCTL_BINARY} show flags',
                       shell=True, verbose=False,
                       ignore_status=False).stdout_text.splitlines()


def get_guest_count():
    """
    Get the current number of SEV-related secure guests

    :returns: The count of guests
    :rtype: int
    :raise: process.CmdError
    """
    r = process.run(f'{SEVCTL_BINARY} show guests',
                    shell=True, verbose=False, ignore_status=False)
    return int(r.stdout_text)


def get_platform_fw_version():
    """
    Get the platform's firmware version

    :returns: The platform's firmware version string
    :rtype: str
    :raise: process.CmdError
    """
    return process.run(f'{SEVCTL_BINARY} show version',
                       shell=True, verbose=False,
                       ignore_status=False).stdout_text


def probe_system(generation=None):
    """
    Probe the system

    :param generation: 'sev' or 'es' or 'snp', if it's None, use the host
                       hw's generation, e.g. if only SEV is supported by
                       host, it probes the system for SEV, and both SEV-ES
                       and SEV-SNP will be skipped
    :type generation: str
    :returns: (True/False, system information probed)
              True if system probed successfully, else False
    :rtype: tuple of (bool, str)
    """
    cmd = f'{SEVCTL_BINARY} ok'
    if generation:
        cmd += f' {generation}'
    r = process.run(cmd, shell=True, verbose=False, ignore_status=True)
    if r.exit_status == 0:
        return True, ANSI_ESCAPE_PATTERN.sub('', r.stdout_text)
    return False, ANSI_ESCAPE_PATTERN.sub('', r.stdout_text + r.stderr_text)


def _form_vmsa_cmd(subcmd, vmsa_file, cpu, userspace,
                   family='', model='', stepping='', firmware=''):
    options = f'--cpu {cpu} --userspace {userspace}'
    if family:
        options += f' --family {family}'
    if model:
        options += f' --model {model}'
    if stepping:
        options += f' --stepping {stepping}'
    if firmware:
        options += f' --firmware {firmware}'

    return f'{SEVCTL_BINARY} vmsa {subcmd} {vmsa_file} {options}'


def build_vmsa_file(vmsa_file, cpu, userspace,
                    family='', model='', stepping='', firmware=''):
    """
    Build a VMSA binary blob and save to the specified file

    :param vmsa_file: Specified VMSA binary blob file
    :type vmsa_file: str
    :param cpu: The cpu number, e.g 1
    :type cpu: str
    :param userspace: Userspace implementation, e.g. qemu
    :type userspace: str
    :param family: The cpu family
    :type family: str
    :param model: The cpu model
    :type model: str
    :param stepping: The cpu stepping
    :type stepping: str
    :param firmware: The path to the ovmf firmware file
    :type firmware: str
    :raise: process.CmdError
    """
    build_cmd = _form_vmsa_cmd('build', vmsa_file, cpu, userspace,
                               family, model, stepping, firmware)
    process.system(build_cmd, shell=True, verbose=False, ignore_status=False)


def update_vmsa_file(vmsa_file, cpu, userspace,
                     family='', model='', stepping='', firmware=''):
    """
    Update an existing VMSA binary file in place

    :param vmsa_file: Specified VMSA binary blob file
    :type vmsa_file: str
    :param cpu: The cpu number, e.g 1
    :type cpu: str
    :param userspace: Userspace implementation, e.g. qemu
    :type userspace: str
    :param family: The cpu family
    :type family: str
    :param model: The cpu model
    :type model: str
    :param stepping: The cpu stepping
    :type stepping: str
    :param firmware: The path to the ovmf firmware file
    :type firmware: str
    :raise: process.CmdError
    """
    update_cmd = _form_vmsa_cmd('update', vmsa_file, cpu, userspace,
                                family, model, stepping, firmware)
    process.system(update_cmd, shell=True, verbose=False, ignore_status=False)


def print_vmsa_file(vmsa_file):
    """
    Print an existing VMSA binary file as JSON

    :param vmsa_file: Specified VMSA binary blob file
    :type vmsa_file: str
    :returns: A JSON string representation of the VMSA file content
    :rtype: str
    :raise: process.CmdError
    """
    return process.run(f'{SEVCTL_BINARY} vmsa show {vmsa_file}',
                       shell=True, verbose=False,
                       ignore_status=False).stdout_text


def generate_launch_session(target_dir, pdh_file, policy, prefix=''):
    """
    Generate a SEV launch session, the following files will be generated
    under the current working directory by default:
        vm_godh.b64, vm_tek.bin, vm_session.b64, vm_tik.bin
    If prefix is set, e.g. prefix=my, then the following files generated:
        my_godh.b64, my_tek.bin, my_session.b64, my_tik.bin

    :param target_dir: Target path where the files are stored
    :type target_dir: str
    :param pdh_file: Path of the file containing the certificate chain
    :type pdh_file: str
    :param policy: 32-bit integer representing the launch policy
    :type policy: int
    :param prefix: Prefix used to identify file names
    :type prefix: str
    :returns: The list of paths to all files generated
    :rtype: list of str
    :raise: process.CmdError if sevctl hits an error
            FileNotFoundError if target_dir doesn't exist
    """
    cwd = os.getcwd()
    os.chdir(target_dir)
    pre_name = f'{prefix}' if prefix else 'vm'
    gen_files = ['session.b64', 'godh.b64', 'tek.bin', 'tik.bin']
    opts = f'--name {prefix}' if prefix else ''
    try:
        process.system(f'{SEVCTL_BINARY} session {opts} {pdh_file} {policy}',
                       shell=True, verbose=False, ignore_status=False)
    finally:
        os.chdir(cwd)

    return [f'{target_dir}/{pre_name}_{name}' for name in gen_files]
