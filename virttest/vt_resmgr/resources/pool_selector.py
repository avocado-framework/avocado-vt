import ast

from virttest.vt_cluster import cluster, selector


class _PoolSelector(object):

    def __init__(self, pool_selectors_param):
        self._pool_selectors = ast.literal_eval(pool_selectors_param)

        if not [d for d in self._pool_selectors if d.get("key") == "access.nodes"]:
            self._add_access_nodes()

        self._match_expressions = []
        for pool_selector in self._pool_selectors:
            key, operator, values = self._convert(pool_selector)
            self._match_expressions.append(
                selector._MatchExpression(key, operator, values)
            )

    def _add_access_nodes(self):
        # Add all partition node tags when access.nodes is not set
        self._pool_selectors.append(
            {
                "key": "access.nodes",
                "operator": "contains",
                "values": " ".join([n.tag for n in cluster.partition.nodes]),
            }
        )

    def _convert(self, pool_selector):
        key = pool_selector.get("key")
        keys = key.split(".")
        operator = pool_selector.get("operator")
        values = pool_selector.get("values")
        if "access.nodes" == key:
            values = [cluster.get_node_by_tag(tag).name for tag in values.split()]
        return keys, operator, values

    def _get_values(self, keys, config):
        config = config["meta"] if keys[0] in config["meta"] else config["spec"]
        for key in keys:
            if key in config:
                config = config[key]
            else:
                raise ValueError(f"Unknown key {key}")
        return config

    def match(self, pool):
        for match_expression in self._match_expressions:
            key = match_expression.key
            op = match_expression.operator
            values = match_expression.values
            config_values = self._get_values(key, pool.pool_config)
            if not selector._Operator.operate(op, config_values, values):
                return False
        return True
