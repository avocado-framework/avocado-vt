# VirtTest Cluster (`vt_cluster`)

The `virttest.vt_cluster` module provides a comprehensive framework for managing distributed
virtualization testing environments. It orchestrates tests across multiple remote machines
from a central controller, enabling scalable test execution in multi-host scenarios.

## Core Concepts

The framework is built around several key concepts:

*   **Cluster:** The central management entity that maintains the state of the
    entire distributed environment. It is a singleton object that tracks all nodes,
    their configurations, and manages partitions with automatic state persistence.
*   **Node:** Represents a single machine within the cluster. Each node can be a
    remote machine that runs agent processes. Nodes handle SSH connections, file
    transfers, agent deployment, and environment setup/cleanup.
*   **Partition:** A logical group of nodes allocated for a specific job or test run.
    This enables resource isolation and execution of multiple tests on different
    node sets.
*   **Selector:** A set of rules used to filter and choose nodes from the cluster
    based on their properties. This allows tests to request nodes with specific
    capabilities (e.g., high memory, specific CPU features).
*   **Agent:** A daemon process running on remote nodes that exposes an XML-RPC API
    for the controller to execute commands, manage services, and coordinate test execution.
*   **Proxy:** The communication layer that handles XML-RPC calls between controller
    and agents, it handles RPC calls and provides a seamless way to invoke methods
    on remote objects.

## Architecture

The `vt_cluster` module follows a controller-agent architecture:

*   **controller:** The main process that orchestrates the tests. It holds the `Cluster`
    object, which knows about all registered nodes.
*   **Agents:** Remote nodes that execute the actual test commands. The `Node` class
    on the controller is responsible for setting up and managing the agent on the
    corresponding remote machine.

### Communication

*   **RPC:** Commands are sent from the controller to agents using XML-RPC. The `proxy.py`
    module implements a client proxy.
*   **Session & File Management:** SSH and SCP are used for initial agent setup,
    file transfers (including copying necessary libraries and collecting logs),
    and managing the agent daemon's lifecycle.

### State Persistence

The state of the cluster (including the list of nodes, their configuration, and
active partitions) is persisted to a `cluster_env` file in the backend data directory.
This state is serialized using `pickle`, allowing it to be restored across different processes.

## How It Works

1.  **Cluster Initialization (Pre-Test Global Setup):**
    a.  `Node` objects are created for all physical machines.
    b.  The agent environment is set up and the agent daemon is started on
        **each node individually**.
    c.  **Only after an agent has successfully started** is the corresponding
        `Node` object registered with the central `cluster`.
    d.  After all healthy nodes are registered, `node_properties.save_properties()`
        is called. This queries all registered agents and populates a metadata
        file with their system details. This step is **mandatory** for the
        selector to function.
2.  **Test Execution with Selection:**
    a.  A test begins.
    b.  It calls `select_node`, providing the test node from candidates.
    c.  The selector reads the pre-loaded metadata file to find a node that matches
        the specified criteria.
3.  **Partitioning and Test Run:**
    a.  If a suitable node is found, a **new partition is created**, and the
        selected node is added to it.
    b.  If no matching node is found, the test will be failed.
    c.  The test proceeds by interacting with the selected node in its partition.
4.  **Cleanup:** After the test, the node is released from the partition.
    After all tests are complete, the global teardown process stops all agents.

## Module Structure

*   `__init__.py`: Core cluster management with `_Cluster` and `_Partition` classes.
    Provides cluster state persistence, node registration, and partition management.
    Exports the global `cluster` instance for application use.
*   `node.py`: Node management with the `Node` class and `NodeError` exception.
    Handles SSH connections, agent deployment, environment setup/cleanup, and
    file transfer operations. Includes comprehensive docstrings with parameter types.
*   `selector.py`: Implements the node selection engine, allowing tests to
    filter nodes based on properties criteria.
*   `node_properties.py`: Manages the creation and loading of node properties from
    the cluster's active agents.
*   `proxy.py`: XML-RPC communication layer with `_ClientProxy` and `ServerProxyError`.
    Implements transparent method calls for distributed operations.
*   `logger.py`: Implements a centralized logging server that collects log records
    from all nodes in the cluster. It provides a unified view of events across
    the distributed environment.

## Centralized Logging

To simplify debugging and monitoring in a distributed environment, `vt_cluster`
includes a centralized logging mechanism implemented in `logger.py`.

*   **Logger Server:** The controller node runs a `LoggerServer` that listens for
    log records sent from remote agents.
*   **Secure Transmission:** Log records are serialized to JSON before being sent
    over the network. This ensures that the data is transmitted securely and avoids
    the vulnerabilities associated with `pickle`.
*   **Unified View:** The server receives records from all nodes, tags them with their
    origin (node name and IP address), and logs them to the controller's output. This
    provides a single, chronological stream of logs from the entire cluster,
    making it easier to trace issues across multiple machines.

### Unified Log Structure

Every log line originating from a worker node consists of two distinct parts separated by a pipe symbol (`|`):

```
[Controller-Side Log Information] | [Proxied Worker Log Information]
```

**Complete Format:**
```
{asctime} {module} {lineno} {levelname} | {nodename}({address}) {asctime} {module} {levelname} | {msg}
```

**Field Definitions:**
- **`{asctime}`**: Timestamp in format `YYYY-MM-DD HH:MM:SS,sss`
  - First instance: When the controller logged the event
  - Second instance: Original timestamp from the worker log
- **`{module}`**: Name of the code module that generated the log
- **`{lineno}`**: Line number where the log was processed on the controller
- **`{levelname}`**: Log level (e.g., `INFO`, `DEBUG`, `ERROR`)
- **`{nodename}`**: Name of the worker node that sent the log (e.g., `node1`)
- **`{address}`**: IP address of the worker node
- **`{msg}`**: Original log message payload from the worker node

**Example Log Entry:**
```
[stdlog] 2024-11-25 21:11:46,122 avocado.test logger L0075 INFO | node1(192.168.122.101) 2024-11-25 21:11:46,122 avocado.service.instance_drivers.qemu INFO | <Instance: By2KZRPGZ105YuIJ> Running qemu command (reformatted)
```

**Breakdown:**
- **Controller Info**: `2024-11-25 21:11:46,122 avocado.test logger L0075 INFO`
  - Controller's `avocado.test` module recorded this event at `21:11:46,122`
- **Worker Info**: `node1(192.168.122.101) 2024-11-25 21:11:46,122 avocado.service.instance_drivers.qemu INFO | <Instance: By2KZRPGZ105YuIJ> Running qemu command (reformatted)`
  - Original log from worker `node1` with IP `192.168.122.101`
  - Generated by `avocado.service.instance_drivers.qemu` module
  - Contains the actual log message about running a QEMU command

## Node Selector

The `vt_cluster` module includes a node selector for dynamically choosing nodes
from a cluster based on their properties. This is useful for tests that have
specific hardware or software requirements. The selection logic is implemented
in `selector.py`.

### Selector Syntax

The selector uses a list of dictionaries, where each dictionary represents a
requirement. The dictionary has the following keys:

*   `key`: The metadata attribute to check (e.g., `"memory_gb"`).
*   `operator`: The comparison operator (e.g., `">="`, `"contains"`).
*   `values`: The value to compare against.

A full demonstration of its use is available in the example below.

## Usage Example

The following example demonstrates how to initialize the cluster, register nodes,
create a partition, and interact with remote agents, while also running the
centralized logger server.

```python
"""
Example of how to use the vt_cluster framework with centralized logging.

This example demonstrates:
1.  Creating and starting agents on nodes.
2.  Registering healthy nodes with the cluster.
3.  Saving properties from the registered nodes.
4.  Running a test that selects a node, partitions it, and uses it.
"""
import logging
import sys

from virttest.vt_cluster import cluster, node_properties
from virttest.vt_cluster.node import Node
from virttest.vt_cluster.logger import LoggerServer
from virttest.vt_cluster.selector import select_node

# 1. Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

# Start the centralized logger server
# Agents will be configured to send their logs here.
LOGGER_HOST = "192.168.122.100"
LOGGER_PORT = 8888
logger_server = LoggerServer((LOGGER_HOST, LOGGER_PORT), logger=logger)
logger_server.start()
logger.info(f"Logger server started at {LOGGER_HOST}:{LOGGER_PORT}")

# 2. Define node configurations
# In a real scenario, this would come from a config file.
# The agent on the node would be configured to connect to the logger server.
node1_params = {
    "address": "192.168.122.101",
    "hostname": "localhost1",
    "username": "root",
    "password": "password",
    "proxy_port": "8000",
    "shell_port": "22",
}
node2_params = {
    "address": "192.168.122.102",
    "hostname": "localhost2",
    "username": "root",
    "password": "password",
    "proxy_port": "8000",
    "shell_port": "22",
}

# 3. Set up agents and register ONLY healthy nodes with the cluster
all_nodes = [
    Node(params=node1_params, name="node1"),
    Node(params=node2_params, name="node2")
]

for node in all_nodes:
    try:
        logger.info(f"Attempting to set up and start agent on {node.name}...")
        node.setup_agent_env()
        node.start_agent_server()
        cluster.register_node(name=node.name, node=node)
        logger.info(f"Node {node.name} is healthy and registered.")
    except Exception as e:
        logger.error(f"Could not set up {node.name}, it will be unavailable. Error: {e}")

# --- Cluster is now ready for tests ---
if not cluster.get_all_nodes():
    logger.critical("No nodes were successfully registered. Aborting test run.")
    logger_server.stop()
    sys.exit(1)

# 4. Save the properties from all healthy, registered nodes. This is REQUIRED for the selector.
logger.info("Saving properties from all registered nodes...")
node_properties.save_properties()
logger.info("Properties saved successfully.")

# --- Test execution begins ---
partition = None
try:
    partition = cluster.create_partition()
    for node in all_nodes:
        # 5. Select a node from the available free nodes in the cluster
        logger.info("Test started. Attempting to select a node...")
        selectors = '[{"key": "cpu_vendor_id", "operator": "eq", "values": "GenuineIntel"}]'
        selected_node = select_node(cluster.get_all_nodes(), selectors=selectors)

        if not selected_node:
            raise RuntimeError("No suitable node found in the cluster. Skipping test.")

        logger.info(f"Successfully selected node: {selected_node.name}")

        # 6. Add the selected node to it
        partition.add_node(selected_node)
        logger.info(f"Node {selected_node.name} added to partition.")

    for node in partition.nodes:
        # 7. Interact with the node
        logger.info(f"Starting logger client on {node.name}...")
        node.proxy.core.start_log_redirection(LOGGER_HOST, LOGGER_PORT)
        greeting = selected_node.proxy.examples.hello.ping()
        logger.info(f"Service Response: {greeting}")

except Exception as e:
    logger.error(f"An error occurred during test execution: {e}")

finally:
    # 8. Clean up the partition, releasing the node
    if partition:
        for node in partition.nodes:
            logger.info(f"Stopping logger client on {node.name}...")
            node.proxy.core.stop_log_redirection()

        cluster.remove_partition(partition)
        logger.info("Partition cleared.")

# --- Global cluster cleanup ---
logger.info("Tearing down all cluster nodes...")
for node in all_nodes:
    try:
        node.stop_agent_server()
        node.cleanup_agent_env()
        cluster.unregister_node(node.name)
    except Exception as e:
        logger.error(f"Error cleaning up {node.name}: {e}")
logger.info("Stopping logger server...")
logger_server.stop()
