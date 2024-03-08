from .vt_resmgr import vt_resmgr


class ImageNotFound(Exception):
    def __init__(self, image_id):
        self._id = image_id

    def __str__(self):
        return 'Cannot find the pool(id="%s)"' % self._id


class UnknownImageType(Exception):
    def __init__(self, image_type):
        self._type = image_type

    def __str__(self):
        return 'Unknown image type "%s"' % self._type


def create_image(config):
    """
    Create a logical image without any specific storage allocation,

    :param config: The image's meta and spec data
    :type config: dict
    :return: The image id
    :rtype: string
    """
    pass


def destroy_image(image_id):
    """
    Destroy the logical image, the specific storage allocation
    will be released, note the image's backing image will not be
    touched

    :param image_id: The resource id
    :type image_id: string
    """
    pass


def get_image(image_id):
    """
    Get all information for a specified image

    :param image_id: The image id
    :type image_id: string
    :return: All the information of an image, e.g.
             {
               'meta': {
                 'id': 'image1',
                 'backing': 'image2'
               },
               'spec': {
                 'name': 'stg',
                 'format': 'qcow2',
                 'backing': {
                    The backing's information here
                 },
                 'volume': {
                   'meta': {
                     'id': 'nfs_vol1'
                   },
                   'spec': {
                     'pool': 'nfs_pool1',
                     'type': 'volume',
                     'size': 65536,
                     'name': 'stg.qcow2',
                     'path': [{'node1': '/mnt1/stg.qcow2'},
                              {'node2': '/mnt2/stg.qcow2'}],
                   }
                 }
               }
            }
    :rtype: dict
    """
    pass


def update_image(image_id, config):
    """
    Update an image, the command format:
      {'action': arguments}, in which
    the 'action' can be the following for a qemu image:
      'create': qemu-img create
      'destroy': Remove the allocated resource
      'convert': qemu-img convert
      'snapshot': qemu-img snapshot
      'resize': qemu-img resize
    arguments is a dict object which contains all related settings for a
    specific action

    Examples:
      qemu-img create
        {'create': }
      qemu-img convert
        {'convert': }

    :param image_id: The image id
    :type image_id: string
    :param config: The specified action and its arguments
    :type config: dict
    """
    pass
