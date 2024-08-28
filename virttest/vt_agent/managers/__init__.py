import logging

from .connect import ConnectManager
from .console import ConsoleManager

connect_mgr = ConnectManager()
console_mgr = ConsoleManager()

LOG = logging.getLogger("avocado.service." + __name__)

# workaround to skip the failure of the import managers
try:
    from .image import ImageHandlerManager
    from .resource_backing import ResourceBackingManager

    resbacking_mgr = ResourceBackingManager()
    image_handler_mgr = ImageHandlerManager()
except ImportError as e:
    LOG.warning(f"Failed to import managers: {e}")
