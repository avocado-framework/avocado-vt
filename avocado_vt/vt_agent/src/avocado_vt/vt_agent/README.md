# Avocado VT Agent (vt_agent)

The Avocado VT Agent (`vt_agent`) is a lightweight, extensible RPC agent designed to be installed and run on remote test machines. It allows for the remote execution of predefined functions and custom services, facilitating test automation within the Avocado VT framework.

This agent is packaged as a separate, standalone distribution (`avocado-vt-agent`) that installs itself into the `avocado_vt` namespace.

## Installation

Before running the agent, it must be installed using `pip`. This is typically done on a remote machine where tests will be executed.

### Dependencies

The agent requires the main `avocado-framework-plugin-vt` package to be available, as it relies on shared libraries from the `virttest` package. This dependency should be handled automatically if the agent is installed from a properly configured package.

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
python -m avocado_vt.vt_agent --host <address> --port <port> --pid-file /path/to/agent.pid
```

**Command-line Arguments:**

*   `--host <address>`: The IP address for the agent to listen on. Defaults to `0.0.0.0` (all interfaces).
*   `--port <port>`: The port number for the agent to listen on. Defaults to `8000`.
*   `--pid-file <path>`: (Required) Path to write the agent's Process ID (PID).

**Example:**
```bash
python -m avocado_vt.vt_agent --host 0.0.0.0 --port 8001 --pid-file ./vt_agent.pid &
```

## Features

*   XML-RPC based communication.
*   Core API for agent control (e.g., status, shutdown).
*   Dynamically loads custom services from the `services` directory.
*   Threaded server to handle multiple client requests concurrently.
*   Logging for agent operations and service execution.

## Checking Agent Status

You can check if the agent is alive and responsive using an XML-RPC client to call the `api.is_alive` method. Note that the agent's API is registered directly at the root.

**Example Python client:**
```python
import xmlrpc.client

try:
    # Replace 'localhost' and '8001' with the agent's host and port
    agent_proxy = xmlrpc.client.ServerProxy("http://localhost:8001/", allow_none=True)

    if agent_proxy.api.is_alive():
        print("vt_agent is alive and responding.")
    else:
        print("api.is_alive() returned False (unexpected).")

except ConnectionRefusedError:
    print("Connection refused. Is vt_agent running at the specified address and port?")
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
*   **API (`services/api.py`)**: Defines built-in functions callable on the agent itself (e.g., `api.quit`, `api.start_logger_client`).
*   **Application (`app/`)**: Manages command-line arguments and the main execution flow.
*   **Services (`services/`)**: Contains dynamically loaded service modules. Each `.py` file (not `__init__.py`) in this directory (and its subdirectories) is treated as a service module. Functions within these modules become callable RPC methods, namespaced by their module path (e.g., `examples.hello.say_hello`).

## Developing Services

1.  **Create a Python file** (e.g., `my_service.py`) inside the `src/avocado_vt/vt_agent/services/` directory or a subdirectory.
2.  **Define functions** within your Python file. These functions will be exposed as RPC methods.
    *   Example `my_service.py`:
        ```python
        import logging
        LOG = logging.getLogger("avocado.agent." + __name__)

        def do_something(param1, param2="default"):
            LOG.info(f"my_service.do_something called with: {param1}, {param2}")
            result = f"Processed {param1} and {param2}"
            return {"status": "success", "result": result}
        ```
3.  **Logging**: Use `logging.getLogger("avocado.agent." + __name__)` to get a logger instance that integrates with the agent's logging.
4.  **Naming**: If your file is `services/custom/my_service.py`, its functions will be callable like `custom.my_service.do_something`.
5.  The agent will automatically discover and load your service when it starts.

## Remote Logging

The agent provides an API to stream logs from services back to a client:
*   `api.start_logger_client(host, port)`: Tells the agent to start sending logs to a socket listener at the specified `host` and `port`.
*   `api.stop_logger_client()`: Stops the log streaming.

A corresponding log server/listener needs to be running on the client side to receive these logs.

## Temporary Files

*   Services can request temporary directories via `from avocado_vt.vt_agent.core import data_dir; temp_path = data_dir.get_tmp_dir()`.
*   The agent has an API endpoint `api.cleanup_tmp_files(path_pattern)` which can be used to clean up specific temporary files or directories.
