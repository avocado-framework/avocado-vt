class ClientError(Exception):
    pass


class MonitorError(Exception):
    pass


class MonitorConnectError(MonitorError):
    def __init__(self, monitor_name):
        MonitorError.__init__(self)
        self.monitor_name = monitor_name

    def __str__(self):
        return "Could not connect to monitor '%s'" % self.monitor_name


class MonitorSocketError(MonitorError):
    def __init__(self, msg, e):
        Exception.__init__(self, msg, e)
        self.msg = msg
        self.e = e

    def __str__(self):
        return "%s    (%s)" % (self.msg, self.e)


class MonitorLockError(MonitorError):
    pass


class MonitorProtocolError(MonitorError):
    pass


class MonitorCmdError(MonitorError):
    pass


class MonitorNotSupportedError(MonitorError):
    pass


class MonitorNotSupportedCmdError(MonitorNotSupportedError):
    def __init__(self, monitor, cmd):
        MonitorError.__init__(self)
        self.monitor = monitor
        self.cmd = cmd

    def __str__(self):
        return "Not supported cmd '%s' in monitor '%s'" % (self.cmd, self.monitor)


class MonitorNotSupportedMigCapError(MonitorNotSupportedError):
    pass


class HumanCmdError(MonitorCmdError):
    def __init__(self, cmd, out):
        MonitorError.__init__(self, cmd, out)
        self.cmd = cmd
        self.out = out

    def __str__(self):
        return "Human monitor command %r failed    " "error message: %r)" % (
            self.cmd,
            self.out,
        )


class QMPCmdError(MonitorCmdError):
    def __init__(self, cmd, qmp_args, data):
        MonitorCmdError.__init__(self, cmd, qmp_args, data)
        self.cmd = cmd
        self.qmp_args = qmp_args
        self.data = data

    def __str__(self):
        return "QMP command %r failed    (arguments: %r,    " "error message: %r)" % (
            self.cmd,
            self.qmp_args,
            self.data,
        )


class QMPEventError(MonitorError):
    def __init__(self, cmd, qmp_event, vm_name, name):
        MonitorError.__init__(self, cmd, qmp_event, vm_name, name)
        self.cmd = cmd
        self.qmp_event = qmp_event
        self.name = name
        self.vm_name = vm_name

    def __str__(self):
        return "QMP event %s not received after %s (monitor '%s.%s')" % (
            self.qmp_event,
            self.cmd,
            self.vm_name,
            self.name,
        )
