"""
RPC (Remote Procedure Call) core functionality for the Avocado VT Agent.

This package provides the XML-RPC server infrastructure and service management
capabilities for the agent. It includes:

- server: XML-RPC server implementation with custom error handling and
  threading support for concurrent request processing
- service: Dynamic service loading and registration system for external
  service modules

The RPC system allows remote clients to invoke agent functions and services
through standardized XML-RPC protocols, enabling distributed testing and
automation workflows.
"""

# pylint: disable=E0611
from avocado_vt.agent.core.rpc import server, service
