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
# Copyright: Red Hat Inc. 2013-2014
# Author: Lucas Meneghel Rodrigues <lmr@redhat.com>

# -*- coding: utf-8 -*-

import os
import sys


def getstatusoutput(cmd):
    """Return (status, output) of executing cmd in a shell."""
    pipe = os.popen("{ " + cmd + "; } 2>&1", "r")
    text = pipe.read()
    sts = pipe.close()
    if sts is None:
        sts = 0
    if text[-1:] == "\n":
        text = text[:-1]
    return sts, text


class DocBuildError(Exception):
    pass


# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
root_path = os.path.abspath(os.path.join("..", ".."))
sys.path.insert(0, root_path)
_sphinx_apidoc = getstatusoutput("which sphinx-apidoc")[1].strip()
_output_dir = os.path.join(root_path, "docs", "source", "api")
_api_dir = os.path.join(root_path, "virttest")
_status, _output = getstatusoutput(
    "%s -o %s %s" % (_sphinx_apidoc, _output_dir, _api_dir)
)
if _status:
    raise DocBuildError("API rst auto generation failed: %s" % _output)

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.coverage",
]

master_doc = "index"
project = "Avocado VT"
copyright = "2014, Red Hat"

version_file = os.path.join(root_path, "VERSION")
VERSION = open(version_file, "r").read().strip()
version = VERSION
release = VERSION

# on_rtd is whether we are on readthedocs.org, this line of code grabbed from
# docs.readthedocs.org
on_rtd = os.environ.get("READTHEDOCS", None) == "True"

if not on_rtd:  # only import and set the theme if we're building docs locally
    try:
        import sphinx_rtd_theme

        html_theme = "sphinx_rtd_theme"
        html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]
    except ImportError:
        html_theme = "default"

htmlhelp_basename = "avocadodoc"

latex_documents = [
    (
        "index",
        "avocado.tex",
        "Avocado Virt Test Compatibility Layer Documentation",
        "Lucas Meneghel Rodrigues",
        "manual",
    ),
]

man_pages = [
    (
        "index",
        "avocado",
        "Avocado Virt Test Compatibility Layer Documentation",
        ["Lucas Meneghel Rodrigues"],
        1,
    )
]

texinfo_documents = [
    (
        "index",
        "avocado",
        "Avocado Virt Test Compatibility Layer",
        "Lucas Meneghel Rodrigues",
        "avocado",
        "Avocado Virtualization Testing (VT) plugin",
        "Testing",
    ),
]

# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {
    "http://docs.python.org/": None,
    "http://avocado-framework.readthedocs.org/en/latest/": None,
}

autoclass_content = "both"
highlight_language = "none"
