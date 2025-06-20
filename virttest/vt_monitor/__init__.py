"""
Virtual machine monitor interface module.

This package provides classes and utilities for interfacing with virtual machine
monitors, including QMP (QEMU Machine Protocol) and human-readable monitor interfaces.
It handles connection management, command execution, and event handling for VM monitoring.

Main components:
- api: High-level connection controller interface
- client: Monitor client implementations (QMP, Human)
- errors: Exception classes for monitor operations
"""

from .api import ConnectController
from .client import Monitor, HumanMonitor, QMPMonitor
from .errors import (
    ClientError,
    MonitorError,
    MonitorConnectError,
    MonitorSocketError,
    MonitorLockError,
    MonitorProtocolError,
    MonitorCmdError,
    MonitorNotSupportedError,
    MonitorNotSupportedCmdError,
    MonitorNotSupportedMigCapError,
    HumanCmdError,
    QMPCmdError,
    QMPEventError,
)

__all__ = [
    "ConnectController",
    "Monitor",
    "HumanMonitor", 
    "QMPMonitor",
    "ClientError",
    "MonitorError",
    "MonitorConnectError",
    "MonitorSocketError",
    "MonitorLockError",
    "MonitorProtocolError",
    "MonitorCmdError",
    "MonitorNotSupportedError",
    "MonitorNotSupportedCmdError",
    "MonitorNotSupportedMigCapError",
    "HumanCmdError",
    "QMPCmdError",
    "QMPEventError",
]