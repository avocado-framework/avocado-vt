from .qemu import _QemuImage


_image_classes = dict()
_image_classes[_QemuImage.get_image_type()] = _QemuImage


def get_image_class(image_type):
    return _image_classes.get(image_type)


__all__ = ["get_image_class"]
