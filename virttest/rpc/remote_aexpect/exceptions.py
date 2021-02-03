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

"""Module that holds exceptions used in aexpect"""


class ExpectError(Exception):

    """Generic Expect error"""

    def __init__(self, patterns, output):
        super().__init__(patterns, output)
        self.patterns = patterns
        self.output = output

    def _pattern_str(self):
        if len(self.patterns) == 1:
            return "pattern %r" % self.patterns[0]
        return "patterns %r" % self.patterns

    def __str__(self):
        return ("Unknown error occurred while looking for %s    (output: %r)" %
                (self._pattern_str(), self.output))


class ExpectTimeoutError(ExpectError):

    """Timeout when looking for output"""

    def __str__(self):
        return ("Timeout expired while looking for %s    (output: %r)" %
                (self._pattern_str(), self.output))


class ExpectProcessTerminatedError(ExpectError):

    """Worker terminated while doing some operation"""

    def __init__(self, patterns, status, output):
        super().__init__(patterns, output)
        self.status = status

    def __str__(self):
        return ("Process terminated while looking for %s    "
                "(status: %s,    output: %r)" % (self._pattern_str(),
                                                 self.status, self.output))


class ShellError(Exception):

    """Shell error"""

    def __init__(self, cmd, output):
        super().__init__(cmd, output)
        self.cmd = cmd
        self.output = output

    def __str__(self):
        return ("Could not execute shell command %r    (output: %r)" %
                (self.cmd, self.output))


class ShellTimeoutError(ShellError):

    """Timeout when waiting for command to complete"""

    def __str__(self):
        return ("Timeout expired while waiting for shell command to "
                "complete: %r    (output: %r)" % (self.cmd, self.output))


class ShellProcessTerminatedError(ShellError):

    """
    Raised when the shell process itself (e.g. ssh, netcat, telnet)
    terminates unexpectedly
    """

    def __init__(self, cmd, status, output):
        super().__init__(cmd, output)
        self.status = status

    def __str__(self):
        return ("Shell process terminated while waiting for command to "
                "complete: %r    (status: %s,    output: %r)" %
                (self.cmd, self.status, self.output))


class ShellCmdError(ShellError):

    """
    Raised when a command executed in a shell terminates with a nonzero
    exit code (status)
    """

    def __init__(self, cmd, status, output):
        super().__init__(cmd, output)
        self.status = status

    def __str__(self):
        return ("Shell command failed: %r    (status: %s,    output: %r)" %
                (self.cmd, self.status, self.output))


class ShellStatusError(ShellError):

    """
    Raised when the command's exit status cannot be obtained
    """

    def __str__(self):
        return ("Could not get exit status of command: %r    (output: %r)" %
                (self.cmd, self.output))
