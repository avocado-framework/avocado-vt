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

from .storage import _DirVolumeBacking, _DirPoolConnection

# {pool type: pool class object}
_pool_conn_classes = {
    _DirPoolConnection.POOL_TYPE: _DirPoolConnection,
}

# {pool type: {resource type: resource backing class object}}
_backing_classes = {
    _DirVolumeBacking.RESOURCE_POOL_TYPE: {
        _DirVolumeBacking.RESOURCE_TYPE: _DirVolumeBacking,
    },
}


def get_resource_backing_class(pool_type, resource_type):
    backing_classes = _backing_classes.get(pool_type, {})
    return backing_classes.get(resource_type)


def get_pool_connection_class(pool_type):
    return _pool_conn_classes.get(pool_type)


__all__ = ["get_pool_connection_class", "get_resource_backing_class"]
