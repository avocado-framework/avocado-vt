_image_handler_getters = {}


def get_image_handler(image_type, cmd):
    getter = _image_handler_getters.get(image_type)
    return getter(cmd)


__all__ = ["get_image_handler"]
