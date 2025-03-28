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
# Copyright: Red Hat Inc. 2022
# Authors: Yongxue Hong <yhong@redhat.com>

"""
Module for providing the interface of cluster for virt test.
"""

import ast
import logging
import operator

from virttest.vt_resmgr import resmgr

from . import ClusterError, cluster, node_metadata

LOG = logging.getLogger("avocado." + __name__)


class SelectorError(ClusterError):
    """Generic Selector Error."""

    pass


class OperatorError(ClusterError):
    """Generic Operator Error."""

    pass


class _MatchExpression(object):
    def __init__(self, key, op, values):
        self._key = key
        self._operator = op
        self._values = values

    def __str__(self):
        return " ".join((self.key, self.operator, self.values))

    @property
    def key(self):
        return self._key

    @property
    def operator(self):
        return self._operator

    @property
    def values(self):
        return self._values


class _Operator(object):
    @classmethod
    def operate(cls, name, left, right=None):
        operators_mapping = {
            "<": cls._lt,
            "lt": cls._lt,
            ">": cls._gt,
            "gt": cls._gt,
            "==": cls._eq,
            "eq": cls._eq,
            "contains": cls._contains,
            "not contains": cls._not_contains,
        }
        try:
            if right:
                return operators_mapping[name](left, right)
            return operators_mapping[name](left)
        except KeyError:
            raise OperatorError("No support operator '%s'" % name)

    @staticmethod
    def _lt(left, right):
        return operator.lt(left, right)

    @staticmethod
    def _gt(left, right):
        return operator.gt(left, right)

    @staticmethod
    def _eq(left, right):
        return operator.eq(left, right)

    @staticmethod
    def _contains(left, right):
        if isinstance(right, list):
            return set(left).issuperset(right)
        return operator.contains(left, right)

    @staticmethod
    def _not_contains(left, right):
        return not operator.contains(left, right)


class _Selector(object):
    """
    Handler for selecting the corresponding node from the cluster
    according to the node selectors.
    Node selector is the simplest recommended form of node selection constraint.
    You can add the node selector field to your node specification you want the
    target node to have.

    """

    def __init__(self, node_selectors):
        self._node_selectors = ast.literal_eval(node_selectors)
        self._match_expressions = []
        for node_selector in self._node_selectors:
            self._match_expressions.append(
                _MatchExpression(
                    node_selector.get("key"),
                    node_selector.get("operator"),
                    node_selector.get("values"),
                )
            )

        self._metadata = node_metadata.load_metadata_file()

    def match_node(self, free_nodes):
        """
        Match the corresponding node with the node metadata and node selectors.

        :return: The node obj
        :rtype: vt_cluster.node.Node
        """
        if free_nodes is None:
            return None
        for node_name, meta in self._metadata.items():
            node = cluster.get_node(node_name)
            if node not in free_nodes:
                continue
            for match_expression in self._match_expressions:
                key = match_expression.key
                op = match_expression.operator
                values = match_expression.values
                if key not in meta:
                    raise SelectorError("No support metadata '%s'" % key)
                if not _Operator.operate(op, meta[key], values):
                    break
            else:
                return node
        return None


def select_node(candidates, selectors=None):
    """
    Select the node according to the node selectors.

    :param candidates: The list of candidates for selecting.
    :type candidates: list
    :param selectors: The selectors of node.
    :type selectors: str
    :rtype: vt_cluster.node.Node
    """
    if selectors:
        selector = _Selector(selectors)
        return selector.match_node(candidates)
    return candidates.pop() if candidates else None
