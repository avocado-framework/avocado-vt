import sys
import threading
from traceback import format_exception

# Add names you want to be imported by 'from errors import *' to this list.
# This must be list not a tuple as we modify it to include all of our
# the Exception classes we define below at the end of this file.
__all__ = ['format_error', 'context_aware', 'context', 'get_context',
           'exception_context']


def format_error():
    t, o, tb = sys.exc_info()
    trace = format_exception(t, o, tb)
    # Clear the backtrace to prevent a circular reference
    # in the heap -- as per tutorial
    tb = ''

    return ''.join(trace)


# Exception context information:
# ------------------------------
# Every function can have some context string associated with it.
# The context string can be changed by calling context(str) and cleared by
# calling context() with no parameters.
# get_context() joins the current context strings of all functions in the
# provided traceback.  The result is a brief description of what the test was
# doing in the provided traceback (which should be the traceback of a caught
# exception).
#
# For example: assume a() calls b() and b() calls c().
#
# @error.context_aware
# def a():
#     error.context("hello")
#     b()
#     error.context("world")
#     error.get_context() ----> 'world'
#
# @error.context_aware
# def b():
#     error.context("foo")
#     c()
#
# @error.context_aware
# def c():
#     error.context("bar")
#     error.get_context() ----> 'hello --> foo --> bar'
#
# The current context is automatically inserted into exceptions raised in
# context_aware functions, so usually test code doesn't need to call
# error.get_context().

ctx = threading.local()


def _new_context(s=""):
    if not hasattr(ctx, "contexts"):
        ctx.contexts = []
    ctx.contexts.append(s)


def _pop_context():
    ctx.contexts.pop()


def context(s="", log=None):
    """
    Set the context for the currently executing function and optionally log it.

    :param s: A string.  If not provided, the context for the current function
            will be cleared.
    :param log: A logging function to pass the context message to.  If None, no
            function will be called.
    """
    ctx.contexts[-1] = s
    if s and log:
        log("Context: %s" % get_context())


def base_context(s="", log=None):
    """
    Set the base context for the currently executing function and optionally
    log it.  The base context is just another context level that is hidden by
    default.  Functions that require a single context level should not use
    base_context().

    :param s: A string.  If not provided, the base context for the current
            function will be cleared.
    :param log: A logging function to pass the context message to.  If None, no
            function will be called.
    """
    ctx.contexts[-1] = ""
    ctx.contexts[-2] = s
    if s and log:
        log("Context: %s" % get_context())


def get_context():
    """Return the current context (or None if none is defined)."""
    if hasattr(ctx, "contexts"):
        return " --> ".join([s for s in ctx.contexts if s])


def exception_context(e):
    """Return the context of a given exception (or None if none is defined)."""
    if hasattr(e, "_context"):
        return e._context


def set_exception_context(e, s):
    """Set the context of a given exception."""
    e._context = s


def join_contexts(s1, s2):
    """Join two context strings."""
    if s1:
        if s2:
            return "%s --> %s" % (s1, s2)
        else:
            return s1
    else:
        return s2


def context_aware(fn):
    """A decorator that must be applied to functions that call context()."""
    def new_fn(*args, **kwargs):
        _new_context()
        _new_context("(%s)" % fn.__name__)
        try:
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if not exception_context(e):
                    set_exception_context(e, get_context())
                raise
        finally:
            _pop_context()
            _pop_context()
    new_fn.__name__ = fn.__name__
    new_fn.__doc__ = fn.__doc__
    new_fn.__dict__.update(fn.__dict__)
    return new_fn


def _context_message(e):
    s = exception_context(e)
    if s:
        return "    [context: %s]" % s
    else:
        return ""
