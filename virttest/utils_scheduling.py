"""
Virtualization test utility functions.

:copyright: 2008-2009 Red Hat Inc.
"""
import multiprocessing.pool
import functools


def timeout(timeout):
    """Timeout decorator, parameter in seconds."""
    def timeout_decorator(func):
        """Wrap the original function."""
        @functools.wraps(func)
        def func_wrapper(*args, **kwargs):
            """Closure for function."""
            pool = multiprocessing.pool.ThreadPool(processes=1)
            async_result = pool.apply_async(func, args, kwargs)
            # raises a TimeoutError if execution exceeds timeout
            return async_result.get(timeout)
        return func_wrapper
    return timeout_decorator
