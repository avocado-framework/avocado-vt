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
# Authors: Yongxue Hong <yhong@redhat.com>

"""
This module provides a flexible mechanism for selecting nodes from a cluster
based on a set of specified criteria. It allows users to define complex
selection rules using key-value expressions and logical operators to filter
and identify nodes that match specific metadata attributes. This is primarily
used to dynamically allocate nodes for virt tests based on their
capabilities or configuration.
"""

import ast
import logging
import operator
import json

from virttest.vt_resmgr import resmgr

from . import ClusterError, cluster, node_properties

LOG = logging.getLogger("avocado." + __name__)


class SelectorError(ClusterError):
    """Generic error raised for failures during the selection process."""
    pass


class NodeSelectorError(SelectorError):
    """Error raised for failures specific to node selection."""
    pass


class OperatorError(ClusterError):
    """Error raised for invalid or failed operator executions."""
    pass


class _MatchExpression(object):
    """
    Represents a single selector expression.

    A match expression consists of a key, an operator, and a set of values,
    defining a rule for matching against a target object's attributes.

    :param key: The attribute key to match on the target object.
    :type key: str
    :param op: The operator to use for the comparison.
    :type op: str
    :param values: The value(s) to compare against.
    :type values: any
    """
    def __init__(self, key, op, values):
        self._key = key
        self._operator = op
        self._values = values

    def __str__(self):
        """Return a string representation of the expression."""
        return f"{self.key} {self.operator} {self.values}"

    @property
    def key(self):
        """The attribute key of the expression."""
        return self._key

    @property
    def operator(self):
        """The operator of the expression."""
        return self._operator

    @property
    def values(self):
        """The values of the expression."""
        return self._values


class _Operator(object):
    """
    A static class to safely execute operations based on string names.

    This class maps common operator strings (e.g., '>', 'lt', 'contains')
    to their corresponding functions, providing a controlled interface for
    performing comparisons.
    """
    @classmethod
    def operate(cls, name, left, right=None):
        """
        Executes a named operator on the given operands.

        :param name: The string name of the operator (e.g., '==', 'ne').
        :type name: str
        :param left: The left-hand operand.
        :type left: any
        :param right: The right-hand operand (optional for some operators).
        :type right: any
        :return: The result of the operation.
        :rtype: bool
        :raises OperatorError: If the operator is not supported or if a
                                TypeError occurs during the operation.
        """
        operators_mapping = {
            "<": cls._lt,
            "lt": cls._lt,
            ">": cls._gt,
            "gt": cls._gt,
            "==": cls._eq,
            "eq": cls._eq,
            "!=": cls._ne,
            "ne": cls._ne,
            "contains": cls._contains,
            "not contains": cls._not_contains,
            # TODO: Support more others regular operator and even the customized
        }
        try:
            if right:
                return operators_mapping[name](left, right)
            return operators_mapping[name](left)
        except KeyError:
            raise OperatorError("No support operator '%s'" % name)
        except TypeError as e:
            raise OperatorError(f"Operator '{name}' failed with error: {e}")

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
    def _ne(left, right):
        return operator.ne(left, right)

    @staticmethod
    def _contains(left, right):
        if isinstance(left, list) and isinstance(right, list):
            return all(item in left for item in right)
        return operator.contains(left, right)

    @staticmethod
    def _not_contains(left, right):
        return not _Operator._contains(left, right)


class _Selector(object):
    """
    A generic selector engine that matches a target against a set of rules.

    :param selectors: A list of selector dictionaries, where each dictionary
                      defines a matching rule.
    :type selectors: list
    """
    def __init__(self, selectors):
        self._selectors = selectors
        self._match_expressions = []
        for selector in self._selectors:
            self._match_expressions.append(self._build_expression(selector))

    def _build_expression(self, selector):
        """
        Builds a _MatchExpression from a selector dict.

        :param selector: A dictionary defining the matching rule.
        :type selector: dict
        :return: A match expression object.
        :rtype: _MatchExpression
        """
        return _MatchExpression(
            selector.get("key"),
            selector.get("operator"),
            selector.get("values"),
        )

    def _get_value_from_target(self, target, key):
        """
        Retrieves a value from the target object based on a key.

        This method must be implemented by subclasses to define how values
        are extracted from the target object.

        :param target: The object to extract the value from.
        :type target: any
        :param key: The key or attribute name to look up.
        :type key: str
        :raises KeyError: If the key is not found in the target.
        :return: The value corresponding to the key.
        :rtype: any
        """
        if key not in target:
            raise KeyError(key)
        return target[key]

    def match(self, target):
        """
        Checks if the given target object matches all selector expressions.

        :param target: The object to check.
        :type target: any
        :return: `True` if the target matches all rules, `False` otherwise.
        :rtype: bool
        """
        for match_expression in self._match_expressions:
            try:
                target_value = self._get_value_from_target(
                    target, match_expression.key)
            except KeyError:
                return False  # Key not found in target

            if not _Operator.operate(match_expression.operator,
                                     target_value,
                                     match_expression.values):
                return False  # Operator check failed
        return True


class _NodeSelector(_Selector):
    """
    A handler for selecting a node from the cluster based on node selectors.

    This selector matches against node metadata.

    :param node_selectors: A list of selector dictionaries for matching nodes.
    :type node_selectors: list
    """
    def __init__(self, node_selectors):
        super().__init__(node_selectors)
        self._metadata = node_properties.load_properties()

    def _get_value_from_target(self, target, key):
        """
        Retrieves a value from a node's metadata dictionary.

        :param target: The node's metadata dictionary.
        :type target: dict
        :param key: The metadata key to look up.
        :type key: str
        :return: The metadata value.
        :rtype: any
        """
        return target.get(key)

    def match_node(self, idle_nodes):
        """
        Finds the first free node that matches all selector criteria.

        :param free_nodes: A list of available node objects to check.
        :type free_nodes: list
        :return: The first matching `Node` object, or `None` if no match is found.
        :rtype: vt_cluster.node.Node or None
        """
        if idle_nodes is None:
            return None
        for node_name, meta in self._metadata.items():
            node = cluster.get_node(node_name)
            if node not in idle_nodes:
                continue
            if self.match(meta):
                return node
        return None


class _PoolSelector(_Selector):
    """
    A `_Selector` for finding storage pools based on their configuration.

    This class handles selectors for pools, which have a nested configuration
    structure (`meta` and `spec`). It supports dot-separated keys to access
    nested attributes and can convert node tags to node names.

    :param pool_selectors: A list of selector dictionaries for pools.
    :type pool_selectors: list
    """
    def _build_expression(self, selector):
        """
        Converts values for 'access.nodes' from node tags to node names
        before creating the match expression.
        """
        key = selector.get("key")
        operator = selector.get("operator")
        values = selector.get("values")
        if "access.nodes" in key:
            if isinstance(values, str):
                values = cluster.get_node_by_tag(values).name
            elif isinstance(values, list):
                values = [cluster.get_node_by_tag(tag).name for tag in values]
            else:
                raise ValueError(f"Unsupported values type for '{key}': {values}")
        return _MatchExpression(key, operator, values)

    def _get_value_from_target(self, target, key):
        """
        Retrieves a value from the pool's config, supporting dot-notation.

        It searches for the key in `target['meta']` first, then falls back
        to `target['spec']`.

        :param target: The pool's configuration dictionary.
        :type target: dict
        :param key: A dot-separated key for nested attribute access.
        :type key: str
        :return: The retrieved value.
        :rtype: any
        :raises KeyError: If the key is not found in the pool's config.
        """
        keys = key.split(".")
        # Try searching in 'meta' first
        try:
            value = target["meta"]
            for k in keys:
                value = value[k]
            return value
        except KeyError:
            pass
        # If not in 'meta', try 'spec'
        try:
            value = target["spec"]
            for k in keys:
                value = value[k]
            return value
        except KeyError:
            raise KeyError(f"Key '{key}' not found in pool config")

    def match_pool(self, pools):
        """
        Finds the first pool that matches the selectors.

        :param pools: A list of candidate pool IDs to check.
        :type pools: list
        :return: The ID of the first matching pool, or `None` if no match.
        :rtype: str or None
        """
        for pool_id in pools:
            config = resmgr.get_pool_info(pool_id)
            if self.match(config):
                return pool_id
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
        _selectors = ast.literal_eval(selectors)
        selector = _NodeSelector(_selectors)
        return selector.match_node(candidates)
    return candidates.pop() if candidates else None


def select_resource_pool(pools, pool_selectors):
    _selectors = ast.literal_eval(pool_selectors)
    selector = _PoolSelector(_selectors)
    return selector.match_pool(pools)
