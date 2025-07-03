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

1.  **Initialization:** The `_Cluster` object is initialized, loading any previously
    saved state from the `cluster_env` file.
2.  **Node Registration:** Test configurations define the available nodes,
    which are then registered with the cluster using `cluster.register_node()`.
3.  **Agent Setup:** For each remote node, the controller:
    a.  Connects via SSH.
    b.  Copies the required Python libraries to a directory on the agent.
    c.  Starts the agent server daemon.
4.  **Running a Test:**
    a.  A test requests a `partition` of one or more nodes from the cluster.
    b.  The test interacts with the nodes in its partition through the `Node`
        object and its `proxy` attribute.
    c.  All method calls on the proxy are transparently sent to the remote agent
        for execution (e.g., `node.proxy.foo.boo()`).
5.  **File Operations:** The controller can transfer files to/from remote nodes using
    SCP operations. This includes copying test data, collecting logs, and transferring
    results between nodes and the controller.

## Module Structure

*   `__init__.py`: Core cluster management with `_Cluster` and `_Partition` classes.
    Provides cluster state persistence, node registration, and partition management.
    Exports the global `cluster` instance for application use.
*   `node.py`: Node management with the `Node` class and `NodeError` exception.
    Handles SSH connections, agent deployment, environment setup/cleanup, and
    file transfer operations. Includes comprehensive docstrings with parameter types.
*   `proxy.py`: XML-RPC communication layer with `_ClientProxy` and `ServerProxyError`.
    Implements transparent method calls for distributed operations.

## Usage Example

The following example demonstrates how to initialize the cluster, register nodes,
create a partition, and interact with remote agents.

```python
"""
Example of how to use the vt_cluster framework.

This example demonstrates:
1.  Initializing the cluster.
2.  Defining and registering two remote nodes.
3.  Creating a partition and allocating nodes to it.
4.  Setting up the agent environment on each node.
5.  Starting the agent servers.
6.  Interacting with the agents via the proxy.
7.  Stopping the agents and cleaning up the environment.
"""
from virttest.vt_cluster import cluster
from virttest.vt_cluster.node import Node

# 1. Define node configurations
# In a real scenario, this would come from a config file.
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

# 2. Instantiate and register nodes
node1 = Node(params=node1_params, name="node1")
node2 = Node(params=node2_params, name="node2")

cluster.register_node(name="node1", node=node1)
cluster.register_node(name="node2", node=node2)

# 3. Create a partition and add nodes to it
partition = cluster.create_partition()
partition.add_node(node1)
partition.add_node(node2)

# 4. Setup and manage nodes in the partition
for node in partition.nodes:
    try:
        print(f"Setting up agent on {node.name}...")
        node.setup_agent_env()

        print(f"Starting agent server on {node.name}...")
        node.start_agent_server()

        # 5. Interact with the remote agent
        if node.proxy.core.is_alive():
            print(f"Agent on {node.name} is alive.")
            # Example of a remote call
            greeting = node.proxy.examples.hello.ping()
            print(f"Service Response: {greeting}")
        else:
            print(f"Agent on {node.name} failed to start.")

    except Exception as e:
        print(f"An error occurred on {node.name}: {e}")

    finally:
        # 6. Clean up the node
        print(f"Stopping agent on {node.name}...")
        node.stop_agent_server()
        print(f"Cleaning up environment on {node.name}...")
        node.cleanup_agent_env()

# 7. Clear the partition when done
cluster.remove_partition(partition)

# 8. Unregister the nodes when done
cluster.unregister_node(name="node1")
cluster.unregister_node(name="node2")
```
