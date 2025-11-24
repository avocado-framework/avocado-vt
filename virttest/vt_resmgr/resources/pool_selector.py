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


class PoolSelector(object):

    def __init__(self, pool_selectors_param):
        self._pool_selectors = ast.literal_eval(pool_selectors_param)
        self._match_expressions = []
        for pool_selector in self._pool_selectors:
            key, operator, values = self._convert(pool_selector)
            self._match_expressions.append(
                selector._MatchExpression(key, operator, values)
            )

    @staticmethod
    def _convert(pool_selector):
        key = pool_selector.get("key")
        operator = pool_selector.get("operator")
        values = pool_selector.get("values")
        if "nodes" == key:
            values = [cluster.get_node_by_tag(tag).name for tag in values.split()]
        return key, operator, values

    def _get_values(self, key, config):
        if not config:
            return None
        if key in config:
            return config[key]
        for value in config.values():
            if not isinstance(value, dict):
                continue
            ret = self._get_values(key, value)
            if ret is None:
                continue
            else:
                return ret
        return None

    def match(self, pool):
        for match_expression in self._match_expressions:
            key = match_expression.key
            op = match_expression.operator
            values = match_expression.values
            config_values = self._get_values(key, pool.config)
            if not selector._Operator.operate(op, config_values, values):
                return False
        return True
