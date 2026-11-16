"""Prefer CartConf, with the local Cartesian configuration parser as fallback."""

import logging

__all__ = ["IS_VARIANTER", "Parser", "ParserError"]

try:
    from cartconf.parser import Parser, ParserError

    IS_VARIANTER = True
except ImportError:
    from .cartesian_config import Parser, ParserError

    IS_VARIANTER = False

    logging.getLogger("avocado.app").info(
        "Using the local cartesian_config module; "
        "consider installing and trying cartconf instead"
    )
