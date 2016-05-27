Building test applications
==========================

This is a description of how to build test applications from a test case.

Dependencies
------------

If you write an application that is supposed to be run on the test-target,
place it in the directory `../deps/<name>/` relative to where your test case is
placed. The easiest way to obtain the full path to this directory is by calling
`data_dir.get_deps_dir("<name>")`. Don't forget to add `from virttest import
data_dir` to your test case.

Besides the source file, create a Makefile that will be used to build your test
application. The below example shows a Makefile for the application for the
timedrift test cases. The `remote_build` module requires that a Makefile is
included with all test applications.

.. code-block:: makefile

    CFLAGS+=-Wall
    LDLIBS+=-lrt

    .PHONY: clean

    all: clktest get_tsc

    clktest: clktest.o

    get_tsc: get_tsc.o

    clean:
            rm -f clktest get_tsc

remote_build
------------

To simplify the building of applications on target, and to simplify avoiding the
building of applications on target when they are installed pre-built, use the
`remote_build` module. This module handles both the transfer of files, and
running `make` on target.

A simple example:

.. code-block:: python

    address = vm.get_address(0)
    source_dir = data_dir.get_deps_dir("<testapp>")
    builder = remote_build.Builder(params, address, source_dir)
    full_build_path = builder.build()

In this case, we utilize the `.build()` method, which execute the necessary
methods in `builder` to copy all files to target and run make (if needed). When
done, `.build()` will return the full path on target to the application that
was just built. Be sure to use this path when running your test application, as
the path is changed if the parameters of the build is changed. For example:

.. code-block:: python

    session.cmd_status("%s --test" % os.path.join(full_build_path, "testapp"))

The `remote_build.Builder` class can give you fine-grained control over your
build process as well. Another way to write the above `.build()` invocation
above is:

.. code-block:: python

    builder = remote_build.Builder(params, address, source_dir)
    if builder.sync_directories():
        builder.make()
    full_build_path = builder.full_build_path

This pattern can be useful if you e.g. would like to add an additional command
to run before `builder.make()`, perhaps to install some extra dependencies.
