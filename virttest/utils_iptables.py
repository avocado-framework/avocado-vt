"""
Library to perform iptables configuration for virt test.
"""
import logging

from avocado.utils import process
from avocado.core import exceptions

from . import remote


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
                cmd_output = process.system_output(iptable_check_cmd,
                                                   shell=True)
                exist_rules = cmd_output.strip().split('\n')
            except process.CmdError, info:
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
                    cmd_output = process.system_output(command, shell=True)
                    logging.debug("iptable command success %s", command)
                except process.CmdError, info:
                    raise exceptions.TestError("iptables fails for command "
                                               "locally %s" % command)
        # cleanup server session
        if params:
            server_session.close()
