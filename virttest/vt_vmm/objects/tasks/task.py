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
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>


import abc
import functools


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
