import os
import sys

unittest_dir = os.path.dirname(os.path.abspath(__file__))

try:
    import avocado_i2n
except ImportError:
    avocado_i2n_dir = os.path.join(unittest_dir, '..')
    sys.path.insert(0, avocado_i2n_dir)
