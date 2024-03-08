import logging

from agents import image_agent
from services.resource import info_backing


LOG = logging.getLogger("avocado.service." + __name__)


def handle_image(image_config, config):
    """
    Handle the upper-level image.

    For a qemu image, this function mainly executes qemu-img command,
    such as create/rebase/commit etc.
    """
    # Get all the configuration of the image
    LOG.info(f"Handle image with: {config}")
    return image_agent.handle_image(image_config, config)
