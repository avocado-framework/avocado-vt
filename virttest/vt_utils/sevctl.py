from avocado.utils import process
from avocado.utils.path import find_command


SEVCTL_BINARY = find_command('sevctl', 'sevctl')


def rotate():
    """
    Rotates the Platform Diffie-Hellman (PDH)
      sevctl rotate

    :raise: process.CmdError
    """
    process.system(f'{SEVCTL_BINARY} rotate',
                   shell=True, verbose=False, ignore_status=False)


def reset():
    """
    Resets the SEV platform, this will clear all persistent data
    managed by the platform
      sevctl reset

    :raise: process.CmdError
    """
    process.system(f'{SEVCTL_BINARY} reset',
                   shell=True, verbose=False, ignore_status=False)


def generate(cert_file, key_file):
    """
    Generate a new self-signed OCA certificate and key
      sevctl generate <cert> <key>

    :param cert_file: OCA certificate output file path
    :type cert_file: str
    :param key_file: OCA key output file path
    :type key_file: str
    :raise: process.CmdError
    """
    process.system(f'{SEVCTL_BINARY} generate {cert_file} {key_file}',
                   shell=True, verbose=False, ignore_status=False)


def provision(cert_file, key_file):
    """
    Installs the operator-provided OCA certificate to
    take ownership of the platform
      sevctl provision <cert> <key>

    :param cert_file: Path to the owner's OCA certificate file
    :type cert_file: str
    :param key_file: Path to the owner's OCA private key file
    :type key_file: str
    :raise: process.CmdError
    """
    process.system(f'{SEVCTL_BINARY} provision {cert_file} {key_file}',
                   shell=True, verbose=False, ignore_status=False)


def export(cert_file, full=True):
    """
    Export the SEV or entire certificate chain to a specified file
        sevctl export [FLAGS] <destination>

    :param chain_file: Certificate chain output file path
    :type destination: str
    :param full: Export the entire certificate chain(SEV + CA chain) if True,
                 or export the SEV certificate chain if False
    :type full: bool 
    :raise: process.CmdError
    """
    flags = '--full' if full else ''
    process.system(f'{SEVCTL_BINARY} export {flags} {cert_file}',
                   shell=True, verbose=False, ignore_status=False)


def verify(option='', file=''):
    """
    Verifies the SEV/CA certificate chain
      sevctl verify [OPTION <file>]

    :param options: Available options to choose:
                    --ca : Read CA chain from specified file
                    --oca: Read OCA certificate from specified file
                    --sev: Read SEV chain from specified file
                    If option is '', the well-known public components
                    will be downloaded from their remote locations.
    :type options: str
    :param file: Specified certificate chain file
    :type file: str
    :returns: stdout output of verify command
    :rtype: str
    :raise: process.CmdError
    """
    return process.system_output(f'{SEVCTL_BINARY} verify {option} {file}'.rstrip(),
                                 shell=True, verbose=False, ignore_status=False)


def show(subcmd):
    """
    Display information about the SEV platform
      sevctl show <SUBCOMMAND>

    :param subcmd: Available subcommands:
                   flags:   Show the current platform flags
                   guests:  Show the current number of guests
                   version: Show the platform's firmware version
    :type subcmd: str
    :returns: The output of related subcommands, e.g.
              flags: es
              number of guests: 2
              firmware version: 1.52.4
    :rtype: str
    :raise: process.CmdError
    """
    return process.system_output(f'{SEVCTL_BINARY} show {subcmd}',
                                 shell=True, verbose=False,
                                 ignore_status=False)


def ok(subcmd=''):
    """
    Probe system for SEV support
      sevctl ok [SUBCOMMAND]

    :param subcmd: Available subcommands:
                   es:  SEV + Encrypted State
                   sev: Secure Encrypted Virtualization
                   snp: SEV + Secure Nested Paging
    :type subcmd: str
    :returns: Output of related subcommands
    :rtype: str
    :raise: process.CmdError
    """
    return process.system_output(f'{SEVCTL_BINARY} ok {subcmd}',
                                 shell=True, verbose=False,
                                 ignore_status=False)


def vmsa_write(subcmd, vmsa_file, cpu, userspace,
               family='', model='', stepping='', firmware=''):
    """
    vmsa related commands
        sevctl vmsa build [OPTIONS] <filename> --cpu <cpu> --userspace <userspace>
        sevctl vmsa update [OPTIONS] <filename> --cpu <cpu> --userspace <userspace>

    :param subcmd: Available subcommands:
                   build: Build a VMSA binary blob and
                          save to the specified file
                   update: Update an existing VMSA binary file in place
    :type subcmd: str
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
    """
    options = f'--cpu {cpu} --userspace {userspace}'
    if family:
        options += f' --family {family}'
    if model:
        options += f' --model {model}'
    if stepping:
        options += f' --stepping {stepping}'
    if firmware:
        options += f' --firmware {firmware}'
    process.system(f'{SEVCTL_BINARY} {subcmd} {vmsa_file} {options}',
                   shell=True, verbose=False, ignore_status=False)


def vmsa_read(subcmd, vmsa_file):
    """
    vmsa related commands
        sevctl vmsa show <filename>

    :param subcmd: Available subcommands:
                   show: Print an existing VMSA binary file as JSON
    :type subcmd: str
    :param vmsa_file: Specified VMSA binary blob file
    :type vmsa_file: str
    :returns: A JSON string representation of the vmsa file content
    :rtype: str
    """
    return process.system_output(f'{SEVCTL_BINARY} {subcmd} {vmsa_file}',
                                 shell=True, verbose=False,
                                 ignore_status=False)


def session(pdh_file, policy, prefix=''):
    """
    Generate a SEV launch session
      sevctl session [OPTIONS] <pdh> <policy>

    :param pdh_file: Path of the file containing the certificate chain
    :type pdh_file: str
    :param policy: 32-bit integer representing the launch policy
    :type policy: int
    :param prefix: Prefix used to identify file names, e.g. prefix=dhcert,
                   the following files are generated: dhcert_godh.b64,
                   dhcert_tek.bin, dhcert_session.b64, dhcert_tik.bin
    :type prefix: str
    """
    options = f'--name {prefix}' if prefix else ''
    process.system(f'{SEVCTL_BINARY} session {options} {pdh_file} {policy}',
                   shell=True, verbose=False,ignore_status=False)
