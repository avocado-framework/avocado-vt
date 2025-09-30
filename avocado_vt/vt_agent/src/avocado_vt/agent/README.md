# Avocado VT Agent

The Avocado VT Agent is a lightweight, extensible RPC agent designed to be installed and run on remote test machines. It allows for the remote execution of predefined functions and custom services, facilitating test automation within the Avocado VT framework.

This agent is packaged as a separate, standalone distribution (`avocado-vt-agent`) that installs itself into the `avocado_vt` namespace.

## Installation

Before running the agent, it must be installed using `pip`. This is typically done on a remote machine where tests will be executed.

### Installing the Agent

To build and install the agent, navigate to its directory (the one containing `pyproject.toml`) and use `pip`:

```bash
# From the .../avocado-vt/avocado_vt/vt_agent/ directory
pip install .
```

This command will build the agent and install it into your Python environment.

## Running the Agent

Once installed, the agent can be started as a module. It's recommended to run it as a background service for continuous operation.

```bash
python -m avocado_vt.agent --host <address> --port <port> --pid-file /path/to/agent.pid
```

**Command-line Arguments:**

*   `--host <address>`: The IP address for the agent to listen on. Defaults to `127.0.0.1` (localhost only for security).
*   `--port <port>`: The port number for the agent to listen on. Defaults to `9999`.
*   `--pid-file <path>`: (Required) Path to write the agent's Process ID (PID).

**Example:**
```bash
python -m avocado_vt.agent --host 0.0.0.0 --port 8001 --pid-file ./vt_agent.pid &
```

## Features

*   XML-RPC based communication.
*   Dynamically loads custom services from the `services` directory.
*   Threaded server to handle multiple client requests concurrently.
*   Logging for agent operations and service execution.

## Checking Agent Status

You can check if the agent is alive and responsive using an XML-RPC client to call the `core.is_alive` method.

**Example Python client:**
```python
import xmlrpc.client

try:
    # Replace 'localhost' and '8001' with the agent's host and port
    agent_proxy = xmlrpc.client.ServerProxy("http://localhost:8001/", allow_none=True)

    if agent_proxy.core.is_alive():
        print("Agent is alive and responding.")
    else:
        print("core.is_alive() returned False (unexpected).")

except ConnectionRefusedError:
    print("Connection refused. Is agent running at the specified address and port?")
except xmlrpc.client.Fault as fault:
    print(f"RPC Fault: {fault.faultCode} - {fault.faultString}")
except Exception as e:
    print(f"An error occurred: {e}")

# Example of calling an example service method
try:
    # Assumes the 'examples.hello' service is loaded
    print(f"Executing ping to the agent host")
    greeting = agent_proxy.examples.hello.ping()
    print(f"Service Response: {greeting}")
except xmlrpc.client.Fault as fault:
    print(f"RPC Fault calling service: {fault.faultCode} - {fault.faultString}")
except Exception as e:
    print(f"Error calling service: {e}")
```

## Architecture Overview

*   **Core Agent (`core/`)**: Handles RPC server setup, request dispatching, service loading, logging, and data directory management.
*   **Application (`app/`)**: Manages command-line arguments and the main execution flow.
*   **Services (`services/`)**: Contains dynamically loaded service modules. Each `.py` file (not `__init__.py`) in this directory (and its subdirectories) is treated as a service module. Functions within these modules become callable RPC methods, namespaced by their module path (e.g., `examples.hello.say_hello`).

## Developing Services

1.  **Create a Python file** (e.g., `my_service.py`) inside the `src/avocado_vt/agent/services/` directory or a subdirectory.
2.  **Define functions** within your Python file. These functions will be exposed as RPC methods.
    *   Example `my_service.py`:
        ```python
        import logging

        from avocado_vt.agent.core.logger import DEFAULT_LOG_NAME

        LOG = logging.getLogger(f"{DEFAULT_LOG_NAME}." + __name__)

        def do_something(param1, param2="default"):
            LOG.info(f"my_service.do_something called with: {param1}, {param2}")
            result = f"Processed {param1} and {param2}"
            return {"status": "success", "result": result}
        ```
3.  **Logging**: Use `logging.getLogger(f"{DEFAULT_LOG_NAME}." + __name__)` to get a logger instance that integrates with the agent's logging.
4.  **Naming**: If your file is `services/custom/my_service.py`, its functions will be callable like `custom.my_service.do_something`.
5.  The agent will automatically discover and load your service when it starts.

## Remote Logging

The agent provides a core API to stream logs from services back to a client:
*   `core.start_log_redirection(host, port)`: Tells the agent to start sending logs to a socket listener at the specified `host` and `port`.
*   `core.stop_log_redirection()`: Stops the log streaming.

A corresponding log server/listener needs to be running on the client side to receive these logs.

## Security Considerations

*   **Default Binding**: The agent now defaults to binding on `127.0.0.1` (localhost only) for improved security. To allow external connections, explicitly specify `--host 0.0.0.0`.
*   **Network Access**: When binding to `0.0.0.0`, ensure proper firewall rules and network security controls are in place.
*   **Service Loading**: The agent dynamically loads Python modules from the services directory. Only place trusted service modules in this directory.
