from .qemu import _QemuVirImage

_image_classes = dict()
_image_classes[_QemuVirImage.get_image_type()] = _QemuVirImage


def get_virtual_image_class(image_type):
    return _image_classes.get(image_type)


__all__ = ["get_virtual_image_class"]
