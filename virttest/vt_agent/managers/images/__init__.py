from .qemu import get_qemu_image_handler


_image_handler_getters = {
    "qemu": get_qemu_image_handler,
}


def get_image_handler(image_type, cmd):
    getter = _image_handler_getters.get(image_type)
    return getter(cmd)


__all__ = ["get_image_handler"]
