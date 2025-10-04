# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2025
# Authors: Zhenchao Liu <zhencliu@redhat.com>

import logging

# pylint: disable=E0611
from avocado_vt.agent.managers import image_handler_mgr

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
