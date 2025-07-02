"""
The `core` package for the Avocado VT Agent.

This package provides the central functionalities of the agent, including
the RPC server, service management, data directory handling, and logging setup.
"""

# pylint: disable=E0611
from avocado_vt.agent.core import data_dir, logger, rpc
