""" The file contains some wrappers of common python base-package workflow
    sets that can be repeated throughout the avocado-vt code.
    Please, remember that it is a private module.
    Please, use this module ONLY from other virttest/avocado-vt modules.
"""

import importlib
import importlib.util
import sys
from importlib.machinery import (
    BYTECODE_SUFFIXES,
    EXTENSION_SUFFIXES,
    SOURCE_SUFFIXES,
    ExtensionFileLoader,
    SourceFileLoader,
    SourcelessFileLoader,
)

_LOADERS = (
    (SourceFileLoader, SOURCE_SUFFIXES),
    (SourcelessFileLoader, BYTECODE_SUFFIXES),
    (ExtensionFileLoader, EXTENSION_SUFFIXES),
)


def _load_from_spec(spec):
    """Just for code refactoring, it takes a module spec and does the needed
    things so as to import it into the execution environment.
    :param spec: module spec.
    :type spec: ModSpec
    :returns : Imported module instance
    """
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def import_module(name, path=None):
    """Imports a module named <name> to the execution environment.
    If the module is not in the PYTHONPATH or the local path,
    its path can be determined by the <path> argument.
    :param name: Name of the module that is going to be imported
    :type name: String
    :param path: Path in which the module is located.
                      If None, it will find the module in the current dir
                      and the PYTHONPATH.
    :type path: String, list of strings or  None
    :returns: The imported module
    """
    if path is None:
        if name in sys.builtin_module_names:
            spec = importlib.machinery.BuiltinImporter.find_spec(name, path)
            return _load_from_spec(spec)
        path = sys.path
    elif isinstance(path, str):
        path = [path]

    for entry in path:
        finder = importlib.machinery.FileFinder(entry, *_LOADERS)
        spec = finder.find_spec(name)
        if spec is not None:
            break
    else:
        raise ImportError(f"Couldn't find any module named {name}")
    return _load_from_spec(spec)


def load_source(name, path):
    """Imports the contents of a source file from <path> to the
    execution environment inside a module named <name>.
    :param name: Name of the module that is going to be imported
    :type name: String
    :param path: Path of the source file being imported.
    :type path: String
    :returns: The imported module
    """
    spec = importlib.util.spec_from_file_location(name, path)
    return _load_from_spec(spec)


def lazy_import(name):
    """Allows for an early import that is initialized upon use (lazy import).

    :param name: Name of the module that is going to be imported
    :type name: String
    """
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.find_spec(name)
    if spec is None:
        raise ImportError(f"Could not import module {name}")
    loader = importlib.util.LazyLoader(spec.loader)
    spec.loader = loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module
