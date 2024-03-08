from .qemu import _QemuLogicalImage

_image_classes = dict()
_image_classes[_QemuLogicalImage.get_image_type()] = _QemuLogicalImage


def get_logical_image_class(image_type):
    return _image_classes.get(image_type)


__all__ = ["get_logical_image_class"]
