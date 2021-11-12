import os
import sys

BASE_DIR = os.path.dirname(__file__)
LOG_DIR = os.path.join(BASE_DIR, "log")
AGENT_LOG_FILENAME = os.path.join(LOG_DIR, "agent.log")
SERVICE_LOG_FILENAME = os.path.join(LOG_DIR, "service.log")
LOG_FORMAT = '%(asctime)s %(name)s %(levelname)-5.5s| %(message)s'

sys.path.append(BASE_DIR)
