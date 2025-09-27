_image_classes = {}


def get_logical_image_class(image_type):
    return _image_classes.get(image_type)


__all__ = ["get_logical_image_class"]
