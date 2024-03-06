# :difficulty: simple
# Put this file into $test_provider/tests directory and use
# $ avocado run template --vt-type qemu to execute it.
import logging

LOG = logging.getLogger("avocado.test")


def run(test, params, env):
    """
    Docstring describing template.

    Detailed description of the test:

    1) Get a living VM
    2) Establish a remote session to it
    3) Run the shell command "uptime" on the session.

    :param test: Test object.
    :param params: Dictionary with test parameters.
    :param env: Test environment object.
    """
    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()
    timeout = float(params.get("login_timeout", 240))
    session = vm.wait_for_login(timeout=timeout)
    uptime = session.cmd("uptime")
    LOG.info("Guest uptime result is: %s", uptime)
