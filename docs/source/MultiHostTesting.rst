==============================
Multi-Host Testing
==============================

The Avocado-VT Multi-Host Testing provides a comprehensive solution for distributed virtualization testing across multiple remote machines. This framework orchestrates tests from a central controller, enabling scalable test execution in multi-host scenarios.

.. contents::
   :local:
   :depth: 2

Overview
========

The multi-host testing framework consists of several key components that work together to provide a distributed testing environment:

* **VT Agent**: Lightweight RPC agent deployed on remote test machines
* **VT Cluster**: Central cluster management and node coordination system  
* **VT Resource Manager**: Distributed resource allocation and management
* **Bootstrap Integration**: Automated cluster setup and configuration

This framework follows a controller-agent architecture where a central controller manages multiple remote worker nodes through XML-RPC communication.

Architecture
============

Controller-Agent Model
-----------------------

The framework uses a controller-agent architecture with the following components:

**Controller Node**
   The main process that orchestrates tests. It maintains the cluster state, manages resource allocation, and coordinates test execution across worker nodes.

**Worker Nodes** 
   Remote machines that execute actual test commands. Each worker node runs an agent daemon that exposes an XML-RPC API for the controller.

**Communication Layer**
   XML-RPC based communication between controller and agents, with additional SSH/SCP for file transfers and agent deployment.

Architecture Diagram
--------------------

.. code-block:: text

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                             CONTROLLER NODE                                 │
    │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
    │  │   VT Cluster    │  │  VT Resource    │  │      Test Runner            │  │
    │  │   Manager       │  │   Manager       │  │   (Avocado Framework)       │  │
    │  │                 │  │                 │  │                             │  │
    │  │ • Node Registry │  │ • Pool Manager  │  │ • Test Scheduling           │  │
    │  │ • Partitions    │  │ • Resource      │  │ • Result Collection         │  │
    │  │ • Node Selector │  │   Allocation    │  │ • Log Aggregation           │  │
    │  │ • State Mgmt    │  │ • Backing Coord │  │                             │  │
    │  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
    │           │                     │                          │                │
    │           └─────────────────────┼──────────────────────────┘                │
    │                                 │                                           │
    │  ┌─────────────────────────────────────────────────────────────────────┐    │
    │  │                    Logger Server (Port 8888)                        │    │
    │  │                  • Centralized Log Collection                       │    │
    │  │                  • Real-time Log Streaming                          │    │
    │  └─────────────────────────────────────────────────────────────────────┘    │
    └─────────────────────────────────────────────────────────────────────────────┘
                                       │
                        ┌──────────────┼──────────────┐
                        │              │              │
                     XML-RPC        XML-RPC        XML-RPC
                        │              │              │
                        ▼              ▼              ▼
    ┌─────────────────────────┐ ┌─────────────────────────┐ ┌─────────────────────────┐
    │     WORKER NODE 1       │ │     WORKER NODE 2       │ │     WORKER NODE N       │
    │  ┌─────────────────────┐│ │  ┌─────────────────────┐│ │  ┌─────────────────────┐│
    │  │     VT Agent        ││ │  │     VT Agent        ││ │  │     VT Agent        ││
    │  │   (Port 8000)       ││ │  │   (Port 8000)       ││ │  │   (Port 8000)       ││
    │  │                     ││ │  │                     ││ │  │                     ││
    │  │ • XML-RPC Server    ││ │  │ • XML-RPC Server    ││ │  │ • XML-RPC Server    ││
    │  │ • Service Registry  ││ │  │ • Service Registry  ││ │  │ • Service Registry  ││
    │  │ • Log Streaming     ││ │  │ • Log Streaming     ││ │  │ • Log Streaming     ││
    │  └─────────────────────┘│ │  └─────────────────────┘│ │  └─────────────────────┘│
    │           │             │ │           │             │ │           │             │
    │  ┌─────────────────────┐│ │  ┌─────────────────────┐│ │  ┌─────────────────────┐│
    │  │Resource Backing Mgr ││ │  │Resource Backing Mgr ││ │  │Resource Backing Mgr ││
    │  │                     ││ │  │                     ││ │  │                     ││
    │  │ • Pool Connections  ││ │  │ • Pool Connections  ││ │  │ • Pool Connections  ││
    │  │ • Resource Backings ││ │  │ • Resource Backings ││ │  │ • Resource Backings ││
    │  │ • Local Operations  ││ │  │ • Local Operations  ││ │  │ • Local Operations  ││
    │  └─────────────────────┘│ │  └─────────────────────┘│ │  └─────────────────────┘│
    │           │             │ │           │             │ │           │             │
    │  ┌─────────────────────┐│ │  ┌─────────────────────┐│ │  ┌─────────────────────┐│
    │  │  Resource Pools     ││ │  │  Resource Pools     ││ │  │  Resource Pools     ││
    │  │                     ││ │  │                     ││ │  │                     ││
    │  │ • Storage (NFS)     ││ │  │ • Storage (Local)   ││ │  │ • Storage (iSCSI)   ││
    │  │ • Network (TAP)     ││ │  │ • Network (Bridge)  ││ │  │ • Network (VLAN)    ││
    │  │ • Compute Resources ││ │  │ • Compute Resources ││ │  │ • Compute Resources ││
    │  └─────────────────────┘│ │  └─────────────────────┘│ │  └─────────────────────┘│
    └─────────────────────────┘ └─────────────────────────┘ └─────────────────────────┘

**Communication Flows:**

1. **Control Plane**: Controller → Worker Nodes via XML-RPC (ports 8000+)
2. **Management Plane**: Controller → Worker Nodes via SSH/SCP (port 22) for deployment
3. **Logging Plane**: Worker Nodes → Controller via TCP (port 8888) for log streaming
4. **Data Plane**: Direct resource access between worker nodes and resource pools

**Key Features:**

* **Distributed Architecture**: Horizontal scaling across multiple worker nodes
* **Resource Isolation**: Per-node resource backing with centralized coordination  
* **Fault Tolerance**: Independent worker operation with controller coordination
* **Unified Monitoring**: Centralized logging and cluster state management
* **Dynamic Partitioning**: Flexible test workload distribution and isolation

Core Components
===============

VT Agent (avocado_vt.agent)
----------------------------

The VT Agent is a standalone RPC daemon that runs on remote test machines, providing the execution environment for distributed tests.

Installation and Deployment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The agent is packaged as a separate distribution that installs into the ``avocado_vt`` namespace::

    # Install the agent on remote machines
    pip install /path/to/avocado-vt/avocado_vt/vt_agent/

Running the Agent
~~~~~~~~~~~~~~~~~

Start the agent daemon with required configuration::

    python -m avocado_vt.agent --host 0.0.0.0 --port 8001 --pid-file ./vt_agent.pid

**Command-line Options:**

* ``--host <address>``: IP address for the agent to listen on (default: 127.0.0.1)
* ``--port <port>``: Port number for the agent to listen on (default: 9999)  
* ``--pid-file <path>``: Required path to write the agent's Process ID

Agent Features
~~~~~~~~~~~~~~

* **XML-RPC Communication**: Provides standardized RPC interface for remote operations
* **Dynamic Service Loading**: Automatically discovers and loads service modules from the services directory
* **Threaded Server**: Handles multiple concurrent client requests
* **Resource Management**: Integrates with the distributed resource management system
* **Centralized Logging**: Streams log records back to the controller for unified monitoring

Agent Services
~~~~~~~~~~~~~~

The agent exposes various services through its RPC interface:

**Core Services** (``core.*``)
   * ``core.is_alive()``: Check if agent is responsive
   * ``core.start_log_redirection(host, port)``: Begin streaming logs to controller
   * ``core.stop_log_redirection()``: Stop log streaming
   * ``core.quit()``: Gracefully shutdown the agent

**Resource Services** (``resource.*``)  
   * Resource backing management operations
   * Pool connection lifecycle management
   * Resource allocation and deallocation

**Custom Services**
   Users can add custom service modules to extend agent functionality. Services are automatically discovered and exposed via RPC.

VT Cluster (virttest.vt_cluster)
--------------------------------

The VT Cluster module provides comprehensive cluster management capabilities for distributed virtualization testing.

Core Concepts
~~~~~~~~~~~~~

**Cluster**
   Central management entity that maintains the state of the entire distributed environment. Singleton object that tracks all nodes, configurations, and manages partitions with automatic state persistence.

**Node**  
   Represents a single machine within the cluster. Handles SSH connections, file transfers, agent deployment, and environment setup/cleanup.

**Partition**
   Logical group of nodes allocated for a specific job or test run. Enables resource isolation and execution of multiple tests on different node sets.

**Selector**
   Set of rules used to filter and choose nodes based on their properties. Allows tests to request nodes with specific capabilities.

**Proxy**
   Communication layer that handles XML-RPC calls between controller and agents, providing seamless method invocation on remote objects.

Node Management
~~~~~~~~~~~~~~~

Nodes are managed through the ``Node`` class which provides:

**Connection Management**
   * SSH session establishment and management
   * File transfer operations via SCP
   * Remote command execution

**Agent Lifecycle** 
   * Agent environment setup and package deployment
   * Agent daemon startup and monitoring  
   * Agent shutdown and cleanup

**Configuration**
   Node configuration includes connection parameters, agent settings, and resource access permissions.

Example node configuration:

.. code-block:: python

    node_params = {
        "address": "192.168.122.101",
        "hostname": "worker1", 
        "username": "root",
        "password": "password",
        "proxy_port": "8000",
        "shell_port": "22",
        "agent_base_dir": "/var/run/vt_agent_server"
    }

Cluster Operations
~~~~~~~~~~~~~~~~~~

**Cluster Initialization**:

.. code-block:: python

    from virttest.vt_cluster import cluster
    from virttest.vt_cluster.node import Node
    
    # Create and register nodes
    node1 = Node(params=node1_params, name="node1")
    node1.setup_agent_env()
    node1.start_agent_server()
    cluster.register_node(name=node1.name, node=node1)

**Partition Management**:

.. code-block:: python

    # Create partition for test isolation
    partition = cluster.create_partition()
    partition.add_node(selected_node)
    
    # Test execution
    # ... use nodes in partition ...
    
    # Cleanup
    cluster.remove_partition(partition)

**Node Selection**:

.. code-block:: python

    from virttest.vt_cluster.selector import select_node
    
    # Select nodes based on criteria
    selectors = '[{"key": "cpu_vendor_id", "operator": "eq", "values": "GenuineIntel"}]'
    selected_node = select_node(cluster.get_all_nodes(), selectors=selectors)

State Persistence
~~~~~~~~~~~~~~~~~

The cluster state is automatically persisted to enable recovery across process boundaries::

    # State stored in cluster_env file in backend data directory
    # Includes: node registrations, configurations, active partitions
    # Uses pickle serialization for complete state restoration

Centralized Logging
~~~~~~~~~~~~~~~~~~~

The framework includes centralized logging to simplify debugging across distributed environments:

**Logger Server**
   Controller runs a ``LoggerServer`` that collects log records from all remote agents.

**Log Format**  
   Unified log structure with controller and worker information::
   
    [Controller Info] | [Worker Info] | [Log Message]
    2024-11-25 21:11:46,122 avocado.test logger L0075 INFO | node1(192.168.122.101) 2024-11-25 21:11:46,122 avocado.service INFO | Running qemu command

**Setup Example**:

.. code-block:: python

    from virttest.vt_cluster.logger import LoggerServer
    
    # Start centralized logger
    logger_server = LoggerServer(("192.168.122.100", 8888), logger=logger)
    logger_server.start()
    
    # Configure agents to send logs
    node.proxy.core.start_log_redirection("192.168.122.100", 8888)

VT Resource Manager (virttest.vt_resmgr)
-----------------------------------------

The VT Resource Manager provides distributed resource allocation and management across the cluster environment.

Resource Management Architecture
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Distributed Design**
   * **Controller Side**: ``ResourceManager`` coordinates cluster-wide resource state
   * **Worker Side**: ``ResourceBackingManager`` handles node-local resource operations  
   * **Communication**: Cluster proxy enables controller-worker coordination

**Resource Types**
   The system supports various resource types:
   
   * **Storage Resources**: Volumes, files, directories, NFS shares
   * **Network Resources**: Ports, network connections, TAP interfaces
   * **Pool Resources**: Resource pools for organizing and accessing resources

Resource Lifecycle
~~~~~~~~~~~~~~~~~~

The resource lifecycle follows a well-defined sequence from creation to cleanup:

.. code-block:: text

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                         RESOURCE LIFECYCLE FLOW                             │
    └─────────────────────────────────────────────────────────────────────────────┘

      Controller Node                          Worker Nodes
      ───────────────                          ────────────

    ┌─────────────────┐
    │  1. CREATE      │    ╔══════════════════════════════════════════════════════╗
    │   Resource      │    ║  Resource object created in ResourceManager          ║
    │   Object        │    ║  • Configuration defined                             ║
    │                 │    ║  • UUID assigned                                     ║
    │                 │    ║  • Pool association established                      ║
    └─────────┬───────┘    ╚══════════════════════════════════════════════════════╝
              │
              ▼
    ┌─────────────────┐
    │  2. BIND        │    ╔══════════════════════════════════════════════════════╗
    │   Resource to   │────╬──▶ Node 1: Create backing object                    ║
    │   Worker Nodes  │    ║      └─ Pool connection established                  ║
    │                 │────╬──▶ Node 2: Create backing object                    ║
    │                 │    ║      └─ Pool connection established                  ║
    └─────────┬───────┘    ╚══════════════════════════════════════════════════════╝
              │
              ▼
    ┌─────────────────┐
    │  3. ALLOCATE    │    ╔══════════════════════════════════════════════════════╗
    │   Physical      │────╬──▶ Node 1: Allocate physical resource               ║
    │   Resource      │    ║      • Create storage volume/network interface       ║
    │                 │    ║      • Update resource state                         ║
    │                 │    ║      • Return allocation details                     ║
    └─────────┬───────┘    ╚══════════════════════════════════════════════════════╝
              │
              ▼
    ┌─────────────────┐
    │  4. OPERATIONS  │    ╔══════════════════════════════════════════════════════╗
    │   • Sync state  │────╬──▶ Node 1: Query resource status                    ║
    │   • Get info    │    ║      • Check allocation status                       ║
    │   • Resize      │    ║      • Retrieve resource metadata                    ║
    │   • Clone       │    ║      • Perform resize/clone operations               ║
    └─────────┬───────┘    ╚══════════════════════════════════════════════════════╝
              │
              ▼
    ┌─────────────────┐
    │  5. RELEASE     │    ╔══════════════════════════════════════════════════════╗
    │   Physical      │────╬──▶ Node 1: Release physical resource                ║
    │   Resource      │    ║      • Delete storage volume/network interface       ║
    │                 │    ║      • Update resource state                         ║
    │                 │    ║      • Maintain backing object                       ║
    └─────────┬───────┘    ╚══════════════════════════════════════════════════════╝
              │
              ▼
    ┌─────────────────┐
    │  6. UNBIND      │    ╔══════════════════════════════════════════════════════╗
    │   Resource from │────╬──▶ Node 1: Destroy backing object                   ║
    │   Worker Nodes  │    ║      └─ Close pool connection                        ║
    │                 │────╬──▶ Node 2: Destroy backing object                   ║
    │                 │    ║      └─ Close pool connection                        ║
    └─────────┬───────┘    ╚══════════════════════════════════════════════════════╝
              │
              ▼
    ┌─────────────────┐
    │  7. DESTROY     │    ╔══════════════════════════════════════════════════════╗
    │   Resource      │    ║  Resource object removed from ResourceManager        ║
    │   Object        │    ║  • Configuration cleaned up                          ║
    │                 │    ║  • UUID invalidated                                  ║
    │                 │    ║  • Pool association removed                          ║
    └─────────────────┘    ╚══════════════════════════════════════════════════════╝

**State Transitions:**

* **Created → Bound**: Resource backing objects created on worker nodes
* **Bound → Allocated**: Physical resource created (e.g., disk file, network interface)  
* **Allocated → Operating**: Resource available for test operations
* **Operating → Released**: Physical resource destroyed, backing preserved
* **Released → Unbound**: Backing objects destroyed on worker nodes
* **Unbound → Destroyed**: Resource object removed from controller

**Multi-Node Coordination:**

* **Controller**: Maintains overall resource state and coordinates operations
* **Worker Nodes**: Execute local resource operations through backing objects
* **Pool Connections**: Provide access to shared storage/network resources
* **State Synchronization**: Regular sync operations ensure consistency

**1. Resource Creation**:

.. code-block:: python

    # Create resource from test parameters
    resource_id = resmgr.create_resource_from_params(
        resource_name="test_volume",
        resource_type="volume", 
        resource_params=volume_params
    )

**2. Resource Binding**:

.. code-block:: python

    # Bind resource to worker nodes
    resmgr.bind_resource(resource_id, node_names=["node1", "node2"])

**3. Resource Allocation**:

.. code-block:: python

    # Allocate physical resource
    resmgr.update_resource(resource_id, "allocate", arguments={"node": "node1"})

**4. Resource Operations**:

.. code-block:: python

    # Sync resource state
    resmgr.update_resource(resource_id, "sync")
    
    # Get resource information
    info = resmgr.get_resource_info(resource_id, request="spec.size")

**5. Resource Cleanup**:

.. code-block:: python

    # Release and unbind resource
    resmgr.update_resource(resource_id, "release")
    resmgr.unbind_resource(resource_id)
    resmgr.destroy_resource(resource_id)

Pool Management
~~~~~~~~~~~~~~~

**Pool Configuration**:

.. code-block:: python

    # Define storage pool
    pool_config = {
        "type": "filesystem",
        "nodes": ["node1", "node2"],
        "path": "/shared/storage"
    }

**Pool Operations**:

.. code-block:: python

    # Create and attach pool
    pool_id = resmgr.create_pool_from_params("shared_storage", pool_config)
    resmgr.attach_pool(pool_id)
    
    # Pool lifecycle management
    resmgr.detach_pool(pool_id)
    resmgr.destroy_pool(pool_id)

Resource Backing System
~~~~~~~~~~~~~~~~~~~~~~~

Resources operate through a distributed backing system:

**Backing Objects**
   Node-local implementations that provide actual resource access on worker nodes.

**Pool Connections**  
   Connections to resource pools maintained on worker nodes for resource access.

**State Persistence**
   Resource manager state persisted across test processes to maintain consistency.

Bootstrap Integration
=====================

The multi-host testing framework integrates with Avocado-VT's bootstrap system for automated setup.

Bootstrap Configuration
-----------------------

**Cluster Configuration File**
   JSON configuration file defining cluster topology and resources:

.. code-block:: json

    {
        "hosts": {
            "node1": {
                "address": "192.168.122.101",
                "username": "root", 
                "password": "password",
                "proxy_port": "8000"
            },
            "node2": {
                "address": "192.168.122.102",
                "username": "root",
                "password": "password", 
                "proxy_port": "8000"
            }
        },
        "pools": {
            "storage": {
                "shared_nfs": {
                    "type": "nfs",
                    "server": "192.168.122.100",
                    "export": "/exports/vt"
                }
            }
        }
    }

**Bootstrap Command**::

    # Setup cluster environment during bootstrap
    avocado vt-bootstrap --vt-cluster-config /path/to/cluster.json

Bootstrap Process
-----------------

The bootstrap process automatically:

1. **Load Cluster Configuration**: Parse cluster JSON configuration file
2. **Register Hosts**: Setup and register all configured hosts as cluster nodes  
3. **Setup Managers**: Initialize resource manager with configured pools
4. **Agent Deployment**: Deploy and start agents on all worker nodes
5. **Environment Validation**: Verify cluster health and connectivity

**Bootstrap Code Integration** (``virttest/bootstrap.py``):

.. code-block:: python

    # Setup the cluster environment
    vt_cluster_config = get_opt(options, "vt_cluster_config")
    if vt_cluster_config:
        cluster_config = _load_cluster_config(vt_cluster_config)
        _register_hosts(cluster_config.get("hosts"))
        _setup_managers(cluster_config.get("pools"))

Plugin Integration
------------------

The framework integrates with Avocado through the VT Cluster plugin:

**Plugin Configuration** (``avocado_vt/plugins/vt_cluster.py``):

.. code-block:: python

    parser.add_argument(
        "--vt-cluster-config",
        action="store",
        metavar="CLUSTER_CONFIG", 
        help=(
            "The cluster config json file to be used when "
            "generating the cluster hosts configuration entry."
        ),
    )

**Cluster Manager Integration** (``avocado_vt/plugins/vt_cluster.py``):

.. code-block:: python

    def _cleanup_managers(self, job):
        """
        Performs post-cleanup for the cluster manager.
        """
        try:
            resmgr.teardown()
        except Exception as err:
            raise ClusterManagerCleanupError(err)

Usage Examples
==============

Complete Multi-Host Test Setup
-------------------------------

Here's a complete example demonstrating multi-host test setup and execution:

.. code-block:: python

    import logging
    from virttest.vt_cluster import cluster, node_properties
    from virttest.vt_cluster.node import Node
    from virttest.vt_cluster.logger import LoggerServer
    from virttest.vt_cluster.selector import select_node

    # 1. Setup centralized logging
    logger = logging.getLogger()
    logger_server = LoggerServer(("192.168.122.100", 8888), logger=logger)
    logger_server.start()

    # 2. Define node configurations  
    node_configs = {
        "node1": {
            "address": "192.168.122.101",
            "username": "root",
            "password": "password",
            "proxy_port": "8000",
            "shell_port": "22"
        },
        "node2": {
            "address": "192.168.122.102", 
            "username": "root",
            "password": "password",
            "proxy_port": "8000", 
            "shell_port": "22"
        }
    }

    # 3. Setup and register nodes
    for name, params in node_configs.items():
        try:
            node = Node(params=params, name=name)
            node.setup_agent_env()
            node.start_agent_server() 
            cluster.register_node(name=name, node=node)
            logging.info(f"Node {name} registered successfully")
        except Exception as e:
            logging.error(f"Failed to setup node {name}: {e}")

    # 4. Save node properties for selection
    node_properties.save_properties()

    # 5. Test execution with node selection
    partition = cluster.create_partition()
    try:
        # Select node based on criteria
        selectors = '[{"key": "cpu_vendor_id", "operator": "eq", "values": "GenuineIntel"}]'
        selected_node = select_node(cluster.get_all_nodes(), selectors=selectors)
        
        if selected_node:
            partition.add_node(selected_node)
            
            # Start log redirection
            selected_node.proxy.core.start_log_redirection("192.168.122.100", 8888)

        # Execute test operations
        for node in partition.nodes:
            result = node.proxy.examples.hello.ping()
            logging.info(f"Test result: {result}")
            
    finally:
        # Cleanup
        for node in partition.nodes:
            node.proxy.core.stop_log_redirection()
        cluster.remove_partition(partition)

Resource Management Example
---------------------------

Example of distributed resource management:

.. code-block:: python

    from virttest.vt_resmgr import resmgr

    # 1. Create storage resource
    volume_params = {
        "size": "10G",
        "format": "qcow2", 
        "storage_type": "filesystem"
    }
    
    resource_id = resmgr.create_resource_from_params(
        resource_name="test_disk",
        resource_type="volume",
        resource_params=volume_params
    )

    # 2. Bind to worker nodes
    resmgr.bind_resource(resource_id, node_names=["node1", "node2"])

    # 3. Allocate on specific node  
    resmgr.update_resource(resource_id, "allocate", arguments={"node": "node1"})

    # 4. Use resource in test
    resource_info = resmgr.get_resource_info(resource_id, request="spec")
    logging.info(f"Resource info: {resource_info}")

    # 5. Cleanup
    resmgr.update_resource(resource_id, "release")
    resmgr.unbind_resource(resource_id)
    resmgr.destroy_resource(resource_id)

Configuration and Best Practices
=================================

Cluster Configuration
---------------------

**Network Configuration**
   * Ensure all nodes can communicate on specified ports
   * Configure firewall rules for XML-RPC and SSH traffic
   * Use consistent network addressing across the cluster

**Security Considerations**
   * Agent defaults to localhost binding - use ``--host 0.0.0.0`` for external access
   * Implement proper SSH key management for secure authentication
   * Consider VPN or secure network for multi-host communication

**Resource Planning**
   * Plan resource pools based on test requirements
   * Consider storage and network resource dependencies  
   * Design for resource isolation between test partitions

Performance Optimization
-------------------------

**Agent Configuration**
   * Tune agent timeouts for network conditions
   * Configure appropriate agent base directories for performance
   * Monitor agent resource usage during test execution

**Logging Management**
   * Configure log levels appropriately for distributed debugging
   * Use centralized logging to avoid log collection overhead
   * Implement log rotation for long-running test suites

**Resource Management**
   * Pre-allocate frequently used resources when possible
   * Implement resource cleanup strategies for failed tests
   * Monitor resource usage across the cluster

Troubleshooting
===============

Common Issues
-------------

**Agent Connection Failures**
   * Verify network connectivity between controller and workers
   * Check firewall rules and port accessibility
   * Validate SSH authentication credentials

**Resource Allocation Failures**
   * Check resource pool availability and capacity
   * Verify node access permissions for resources
   * Review resource binding configurations

**Test Execution Issues** 
   * Monitor centralized logs for distributed error patterns
   * Check agent health using ``core.is_alive()`` calls
   * Verify partition and node state consistency

**State Persistence Problems**
   * Ensure proper cleanup of environment files
   * Check file permissions for state persistence directories
   * Validate cluster state after process restarts

Debugging Techniques
--------------------

**Centralized Logging**
   Use the centralized logging system to trace issues across nodes:

.. code-block:: python

    # Enable debug logging on agents
    selected_node.proxy.core.start_log_redirection(host, port)
    
    # Monitor unified logs for distributed patterns
    logger_server = LoggerServer((host, port), logger=debug_logger)

**Agent Health Monitoring**
   Regularly check agent responsiveness:

.. code-block:: python

    # Check agent status
    for node in cluster.get_all_nodes():
        try:
            alive = node.proxy.core.is_alive()
            logging.info(f"Node {node.name} alive: {alive}")
        except Exception as e:
            logging.error(f"Node {node.name} unreachable: {e}")

**Resource State Inspection**  
   Monitor resource manager state:

.. code-block:: python

    # Check resource information
    resource_info = resmgr.get_resource_info(resource_id)
    binding_nodes = resmgr.get_resource_binding_nodes(resource_id)
    
    # Verify pool status
    pool_info = resmgr.get_pool_info(pool_id)

Conclusion
==========

The Avocado-VT Multi-Host Testing Framework provides a robust, scalable solution for distributed virtualization testing. Its modular architecture, comprehensive resource management, and integrated toolchain enable efficient test execution across complex multi-node environments.

Key benefits include:

* **Scalability**: Distributed architecture supports large-scale test environments
* **Flexibility**: Modular design enables customization for specific test requirements  
* **Reliability**: Comprehensive error handling and state management ensure test consistency
* **Observability**: Centralized logging and monitoring provide complete cluster visibility
* **Integration**: Seamless integration with existing Avocado-VT testing workflows

For additional information and advanced usage examples, refer to the individual component documentation and source code in the respective modules.
