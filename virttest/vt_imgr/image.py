import uuid
from abc import ABC, abstractmethod


class _LogicalImage(ABC):
    """
    A logical image could have one or more _Image objects, take qemu
    logical image as an example, it can contain a top _Image object
    and its backing _Image object, in the context of a VM's disk, a
    logical image is the media of the disk, i.e. one logical image
    for one VM's disk
    """

    def __init__(self, top_image_tag):
        self._id = uuid.uuid4()

    @property
    def image_id(self):
        return self._id

    @property
    def image_spec(self):
        pass

    def create_image(self):
        pass

    def destroy_image(self):
        pass

    def handle_image(self):
        pass


class _Image(ABC):
    """
    An image has one storage resource(volume), the cartesian params of
    a image describes this object
    """

    _IMAGE_TYPE = None

    def __init__(self, image_id, image_params):
        self._tag = image_id
        self._initialize(image_params)

    def _initialize(self, image_params):
        pass

    def image_type(cls):
        raise cls._IMAGE_TYPE

    @property
    def image_id(self):
        return self._id

    @property
    def image_spec(self):
        pass

    def create(self):
        pass

    def destroy(self):
        pass
