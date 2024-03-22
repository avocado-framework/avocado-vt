from .qemu import _qemu_image_handler

# from .xen import _xen_image_handler


class _ImageHandlerDispatcher(object):

    def __init__(self):
        self._managers_mapping = dict()
        self._backings_mapping = dict()
        self._pools_mapping = dict()

    def dispatch(self, key):
        return


_image_handler_dispatcher = _ImageHandlerDispatcher()

_image_handler_dispatcher.register(_qemu_image_handler)
# _image_handler_dispatcher.register(_xen_image_handler)
