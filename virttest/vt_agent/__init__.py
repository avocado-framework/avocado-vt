"""
Avocado VT Agent (vt_agent) main package.

This package initializes the vt_agent environment.
The sys.path modification below is intended to ensure that modules within
the agent can resolve imports relative to the agent's root directory.
"""

import sys

from .core.data_dir import get_root_dir

agent_root_dir = get_root_dir()

if agent_root_dir not in sys.path:
    sys.path.append(agent_root_dir)
