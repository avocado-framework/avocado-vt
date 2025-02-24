import logging
from abc import ABCMeta, abstractmethod

import six

LOG = logging.getLogger("avocado." + __name__)


@six.add_metaclass(ABCMeta)
class Setuper(object):
    """
    Virtual base abstraction of setuper.
    """

    #: Skip the cleanup when error occurs
    skip_cleanup_on_error = False

    def __init__(self, test, params, env):
        """
        Initialize the setuper.

        :param test: VirtTest instance.
        :param params: Dictionary with the test parameters.
        :param env: Dictionary with test environment.
        """
        self.test = test
        self.params = params
        self.env = env

    @abstractmethod
    def setup(self):
        """Setup procedure."""
        raise NotImplementedError

    @abstractmethod
    def cleanup(self):
        """Cleanup procedure."""
        raise NotImplementedError


class SetupManager(object):
    """
    Setup Manager implementation.

    The instance can help do the setup stuff before test started and
    do the cleanup stuff after test finished. This setup-cleanup
    combined stuff will be performed in LIFO order.
    """

    def __init__(self):
        self.__setupers = []
        self.__setup_args = None

    def initialize(self, test, params, env):
        """
        Initialize the setup manager.

        :param test: VirtTest instance.
        :param params: Dictionary with the test parameters.
        :param env: Dictionary with test environment.
        """
        self.__setup_args = (test, params, env)

    def register(self, setuper_cls):
        """
        Register the given setuper class to the manager.

        :param setuper_cls: Setuper class.
        """
        if not self.__setup_args:
            raise RuntimeError("Tried to register setuper " "without initialization")
        if not issubclass(setuper_cls, Setuper):
            raise ValueError("Not supported setuper class")
        self.__setupers.append(setuper_cls(*self.__setup_args))

    def do_setup(self):
        """Do setup stuff."""
        for index, setuper in enumerate(self.__setupers, 1):
            try:
                setuper.setup()
            except Exception:
                if setuper.skip_cleanup_on_error:
                    index -= 1
                # Truncate the list to prevent performing cleanup
                # for the setuper without having performed setup
                self.__setupers = self.__setupers[:index]
                raise

    def do_cleanup(self):
        """
        Do cleanup stuff.

        :return: Errors occurred in cleanup procedures.
        """
        errors = []
        while self.__setupers:
            try:
                self.__setupers.pop().cleanup()
            except Exception as err:
                LOG.error(str(err))
                errors.append(str(err))
        return errors
