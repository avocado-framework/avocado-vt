class _LogicalImageManager(object):

    def __init__(self):
        """
        :param params: the reference to the original cartesian params
        """
        self._images = dict()

    def create_logical_image(self, image_tag, params):
        """
        Create a logical image without any storage allocation, based on
        the cartesian params, create all its image objects, e.g. for a
        qemu logical image which has a image chain:
          top image('top') --> backing image('backing')
                |                      |
             resource               resource
        """
        img_cls = self.get_logical_image_class()
        return image_id

    def destroy_logical_image(self, logical_image_id):
        pass

    def clone_logical_image(self, logical_image_id):
        pass

    def update_logical_image(self, logical_image_id, arguments):
        logical_image = self._images[image_id]
        logical_image.update(arguments)


# Add drivers for diff handlers
# Add access permission for images
# serialize
vt_imgr = _LogicalImageManager()
