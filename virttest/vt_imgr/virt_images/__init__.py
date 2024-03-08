from .qemu import _QemuVirtImage

_image_classes = dict()
_image_classes[_QemuVirtImage.get_image_type()] = _QemuVirtImage


def get_virt_image_class(image_type):
    return _image_classes.get(image_type)


__all__ = ["get_virt_image_class"]
