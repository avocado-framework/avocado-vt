import abc
import functools

from .. import migrate_api
from ..objects import instance_state
from ..objects.migration_exception import UnableToMigrateToSelf


class TaskError(Exception):
    pass


def rollback_wrapper(original):
    @functools.wraps(original)
    def wrap(self):
        try:
            return original(self)
        except Exception as ex:
            self.rollback(ex)
            raise TaskError(str(ex))

    return wrap


class Task(metaclass=abc.ABCMeta):
    def __init__(self, instance):
        self._instance = instance
        self._status = None

    @property
    def instance(self):
        return self._instance

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, state):
        self._status = state

    @rollback_wrapper
    def execute(self):
        """Run task's logic, written in _execute() method"""
        return self._execute()

    @abc.abstractmethod
    def _execute(self):
        """Descendants should place task's logic here, while resource
        initialization should be performed over __init__
        """
        pass

    def rollback(self, ex):
        """Rollback failed task
        Descendants should implement this method to allow task user to
        rollback status to state before execute method  was call
        """
        pass
