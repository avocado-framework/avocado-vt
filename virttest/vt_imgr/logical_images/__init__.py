from .qemu import QemuLogicalImage

_logical_image_classes = {
    QemuLogicalImage.IMAGE_TYPE: QemuLogicalImage,
}


def get_logical_image_class(image_type):
    return _logical_image_classes.get(image_type)


__all__ = ["get_logical_image_class"]
