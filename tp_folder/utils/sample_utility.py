"""

SUMMARY
------------------------------------------------------
Utility with functionality shared among some tests.

Copyright: Intra2net AG


INTERFACE
------------------------------------------------------

"""

import time
import logging
log = logging.getLogger('avocado.test.utils')


def sleep(n=10):
    """
    Sleep for `n` seconds.

    :param int n: seconds to sleep
    """
    log.info("Sleeping for %s seconds", n)
    time.sleep(n)
