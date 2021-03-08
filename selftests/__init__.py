import os

#: The base directory for the avocado-vt source tree
BASEDIR = os.path.dirname(os.path.abspath(__file__))
BASEDIR = os.path.abspath(os.path.join(BASEDIR, os.path.pardir))
