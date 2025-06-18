import logging

from managers import image_handler_mgr

LOG = logging.getLogger("avocado.service." + __name__)


def clone_logical_image(logical_image_config, clone_logical_image_config):
    LOG.info(f"Clone the logical image")
    return image_handler_mgr.clone_logical_image(
        logical_image_config, clone_logical_image_config
    )


def update_logical_image(logical_image_config, config):
    """
    Update the logical image.
    """

    LOG.info(f"Update the logical image with command: {config}")
    return image_handler_mgr.update_logical_image(logical_image_config, config)
