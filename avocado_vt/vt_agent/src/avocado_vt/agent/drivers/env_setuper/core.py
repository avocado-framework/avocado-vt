from abc import ABCMeta, abstractmethod

import six


class SetuperError(Exception):
    pass


@six.add_metaclass(ABCMeta)
class Setuper(object):
    """
    Virtual base abstraction of setuper.
    """

    #: Skip the cleanup when error occurs
    skip_cleanup_on_error = False

    def __init__(self, name):
        """
        Initialize the setuper.

        """
        self.name = name

    @abstractmethod
    def setup(self, setup_config={}):
        """Setup procedure."""
        raise NotImplementedError

    @abstractmethod
    def cleanup(self, clean_config={}):
        """Cleanup procedure."""
        raise NotImplementedError
