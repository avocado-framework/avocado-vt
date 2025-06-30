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

import ast

from virttest.vt_cluster import cluster, selector


class PoolSelector(selector._Selector):
    """
    The generic resource pool selector class.
    Called by Pool.meet_resource_request function, check if a pool can meet a resource request.
    Inherits from it when a resource pool needs to handle something special.
    """

    def __init__(self, pool_selector_params):
        pool_selectors = ast.literal_eval(pool_selector_params)
        super().__init__(pool_selectors)

    @staticmethod
    def _build_expression(pool_selector):
        key = pool_selector.get("key")
        operator = pool_selector.get("operator")
        values = pool_selector.get("values")
        if "nodes" == key:
            # Use node names
            values = [cluster.get_node_by_tag(tag).name for tag in values.split()]
        return selector._MatchExpression(key, operator, values)

    def _get_value_from_target(self, config, key):
        """
        Retrieves a value from the pool's configuration.
        """
        if not config:
            return None
        if key in config:
            return config[key]
        for value in config.values():
            if not isinstance(value, dict):
                continue
            ret = self._get_value_from_target(value, key)
            if ret is None:
                continue
            else:
                return ret
        return None
