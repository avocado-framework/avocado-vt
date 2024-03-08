import logging

from managers import image_handler_mgr

LOG = logging.getLogger("avocado.service." + __name__)


def update_image(image_config, config):
    """
    Update the image.
    """

    LOG.info(f"Update the image with command: {config}")
    return image_handler_mgr.update_image(image_config, config)
