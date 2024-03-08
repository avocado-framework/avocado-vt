from .connect import ConnectManager
from .console import ConsoleManager
from .image_manager import ImageHandlerManager
from .resource_backing_manager import ResourceBackingManager

connect_mgr = ConnectManager()
console_mgr = ConsoleManager()
resbacking_mgr = ResourceBackingManager()
image_handler_mgr = ImageHandlerManager()
