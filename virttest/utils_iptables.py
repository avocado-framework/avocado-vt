"""
Library to perform iptables configuration for virt test.
"""
import logging
import re

from avocado.utils import process
from avocado.core import exceptions

from virttest import remote
from virttest import utils_package
from virttest.compat_52lts import decode_to_text
from virttest.staging import service


class Iptables(object):
    """
    class to handle all iptables configurations related methods
    """

    @classmethod
    def setup_or_cleanup_iptables_rules(cls, rules, params=None,
                                        cleanup=False):
        """
        Setup or cleanup for iptable rules, it can be locally or remotely

        :param rules: list of rules
        :param params: dict with server details
        :param cleanup: Boolean value, true to cleanup, false to setup
        """
        commands = []
        # check the existing iptables rules in remote or local machine
        iptable_check_cmd = "iptables -S"
        if params:
            server_ip = params.get("server_ip")
            server_user = params.get("server_user", "root")
            server_pwd = params.get("server_pwd")
            server_session = remote.wait_for_login('ssh', server_ip, '22',
                                                   server_user, server_pwd,
                                                   r"[\#\$]\s*$")
            cmd_output = server_session.cmd_status_output(iptable_check_cmd)
            if (cmd_output[0] == 0):
                exist_rules = cmd_output[1].strip().split('\n')
            else:
                server_session.close()
                raise exceptions.TestError("iptables fails for command "
                                           "remotely %s" % iptable_check_cmd)
        else:
            try:
                cmd_output = decode_to_text(process.system_output(iptable_check_cmd,
                                                                  shell=True))
                exist_rules = cmd_output.strip().split('\n')
            except process.CmdError as info:
                raise exceptions.TestError("iptables fails for command "
                                           "locally %s" % iptable_check_cmd)
        # check rules whether it is really needed to be added or cleaned
        for rule in rules:
            flag = False
            for exist_rule in exist_rules:
                if rule in exist_rule:
                    logging.debug("Rule: %s exist in iptables", rule)
                    flag = True
                    if cleanup:
                        logging.debug("cleaning rule: %s", rule)
                        commands.append("iptables -D %s" % rule)
            if not flag and not cleanup:
                logging.debug("Adding rule: %s", rule)
                commands.append("iptables -I %s" % rule)
        # Once rules are filtered, then it is executed in remote or local
        # machine
        for command in commands:
            if params:
                cmd_output = server_session.cmd_status_output(command)
                if (cmd_output[0] != 0):
                    server_session.close()
                    raise exceptions.TestError("iptables command failed "
                                               "remotely %s" % command)
                else:
                    logging.debug("iptable command success %s", command)
            else:
                try:
                    cmd_output = decode_to_text(process.system_output(command, shell=True))
                    logging.debug("iptable command success %s", command)
                except process.CmdError as info:
                    raise exceptions.TestError("iptables fails for command "
                                               "locally %s" % command)
        # cleanup server session
        if params:
            server_session.close()


def singleton_class(class_name):
    class_instance = {}

    def get_class(*args, **kwargs):
        host = "local"
        if kwargs.get("session"):
            host = "remote"
        if host not in class_instance:
            class_object = class_name(*args, **kwargs)
            class_instance[host] = class_object
        return class_instance[host]
    return get_class


@singleton_class
class Firewalld(object):
    """
    class handle firewalld service
    """
    def __init__(self, session=None):
        """
        Initialize firewalld service by installing and creating service obj

        :param session: ShellSession Object of guest/remote host
        """
        self.service_name = "firewalld"
        self.session = session
        self.option = ""
        if not utils_package.package_install(self.service_name, session=session):
            logging.error("Firewalld package is not available")
        if self.session:
            self.firewalld = "systemctl %s firewalld"
        else:
            self.firewalld = service.Factory.create_service("firewalld")

        if not self.status():
            self.start()

    def status(self):
        """
        Method to get the status of firewalld service
        """
        if self.session:
            self.option = "status"
            cmd = self.firewalld % (self.option)
            status, output = self.session.cmd_status_output(cmd)
            if status == 0:
                return bool(re.search(r"active \(running\)", output))
            else:
                logging.error(output)
                return False
        else:
            return self.firewalld.status()

    def start(self):
        """
        Method to start firewalld service
        """
        if self.session:
            self.option = "start"
            cmd = self.firewalld % (self.option)
            status, output = self.session.cmd_status_output(cmd)
            if status != 0:
                logging.error(output)
        else:
            self.firewalld.start()

    def stop(self):
        """
        Method to stop firewalld service
        """
        if self.session:
            self.option = "stop"
            cmd = self.firewalld % (self.option)
            status, output = self.session.cmd_status_output(cmd)
            if status != 0:
                logging.error(output)
        else:
            self.firewalld.stop()

    def restart(self):
        """
        Method to restart firewalld service
        """
        if self.session:
            self.option = "restart"
            cmd = self.firewalld % (self.option)
            status, output = self.session.cmd_status_output(cmd)
            if status != 0:
                logging.error(output)
        else:
            self.firewalld.restart()


class Firewall_cmd(object):
    """
    class handles firewall-cmd methods
    """
    def __init__(self, session=None):
        """
        initialises the firewall cmd objects

        :param session: ShellSession Object of guest/remote host
        """
        self.session = session
        self.firewalld_obj = Firewalld(session=self.session)
        self.firewall_cmd = "firewall-cmd"
        self.func = process.getstatusoutput
        if self.session:
            self.func = self.session.cmd_status_output

    def command(self, cmd, **dargs):
        """
        Wrapper method to execute firewall-cmd with different options

        :param cmd: firewall-cmd command options
        :param dargs: Additional arguments for the command
        """
        self.cmd = "%s %s" % (self.firewall_cmd, cmd)
        if dargs.get("permanent", False):
            self.cmd += " --permanent"
        # default zone to be public
        zone = dargs.get("zone", "public")
        if zone:
            self.cmd += " --zone=%s" % zone
        self.status, self.output = self.func(self.cmd)
        if self.status != 0:
            logging.error("Failed to execute %s: %s", self.cmd, self.output)
        # Reload the configuration to make effect at once
        if dargs.get("firewalld_reload", True):
            self.reload()

    def lists(self, key='all', **dargs):
        """
        Method to list existing services/ports etc.,

        :param key: key to be listed, eg: all, services etc.,
        :param dargs: Additional arguments for the command

        :return: output of the --list-*
        """
        cmd = "--list-%s" % key
        dargs['firewalld_reload'] = False
        self.command(cmd, **dargs)
        return self.output

    def get(self, key='zones', **dargs):
        """
        Method to get existing zones/services etc.,

        :param key: key to be get from firewall-cmd
        :param dargs: Additional arguments for the command

        :return: output of the --get-*
        """
        cmd = "--get-%s" % key
        dargs['firewalld_reload'] = False
        self.command(cmd, **dargs)
        return self.output

    def add_service(self, service_name, **dargs):
        """
        Method to add services to be permitted by firewall

        :param service_name: service name to be added
        :param dargs: Additional arguments for the command

        :return: True on success, False on failure.
        """
        cmd = "--add-service=%s" % service_name
        self.command(cmd, **dargs)
        return self.status == 0

    def remove_service(self, service_name, **dargs):
        """
        Method to remove services from permitted by firewall

        :param service_name: service name to be added
        :param dargs: Additional arguments for the command

        :return: True on success, False on failure.
        """
        cmd = "--remove-service=%s" % service_name
        self.command(cmd, **dargs)
        return self.status == 0

    def add_port(self, port, protocol, **dargs):
        """
        Method to add port to be permitted by firewall

        :param port: port number to be added
        :param protocol: protocol respective to the port to be added
        :param dargs: Additional arguments for the command

        :return: True on success, False on failure.
        """
        cmd = "--add-port=%s/%s" % (port, protocol)
        self.command(cmd, **dargs)
        return self.status == 0

    def remove_port(self, port, protocol, **dargs):
        """
        Method to remove port from permitted by firewall

        :param port: port number to be added
        :param protocol: protocol respective to the port to be added
        :param dargs: Additional arguments for the command

        :return: True on success, False on failure.
        """
        cmd = "--remove-port=%s/%s" % (port, protocol)
        self.command(cmd, **dargs)
        return self.status == 0

    def reload(self, complete=False):
        """
        Method to reload/complete reload

        :return: True on success, False on failure.
        """
        cmd = "firewall-cmd --reload"
        if complete:
            cmd = "firewall-cmd --complete-reload"
        self.status, self.output = self.func(cmd)

        return self.status == 0
