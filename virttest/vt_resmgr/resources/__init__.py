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

from .storage import DirPool, NfsPool

_pool_classes = {
    DirPool.TYPE: DirPool,
    NfsPool.TYPE: NfsPool,
}


def get_pool_class(pool_type):
    return _pool_classes.get(pool_type)


__all__ = ["get_pool_class"]
