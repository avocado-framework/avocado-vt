# from .connect import ConnectManager
# from .console import ConsoleManager
#
# connect_mgr = ConnectManager()
# console_mgr = ConsoleManager()


from .connect import ConnectManager
from .console import ConsoleManager

connect_mgr = ConnectManager()
console_mgr = ConsoleManager()

try:
    from .image import ImageHandlerManager
    from .resource_backing import ResourceBackingManager
    resbacking_mgr = ResourceBackingManager()
    image_handler_mgr = ImageHandlerManager()
except ImportError:
    pass
