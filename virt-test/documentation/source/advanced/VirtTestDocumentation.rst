.. contents::

================
Virt Test Primer
================

Autotest
========
.. _autotest_introduction:

Introduction
----------------------

It is critical for any project to maintain a high level of software
quality, and consistent interfaces to other software that it uses or
uses it. Autotest is a framework for fully automated testing, that is
designed primarily to test the Linux kernel, though is useful for many
other functions too. It includes a client component for executing tests
and gathering results, and a completely optional server component for
managing a grid of client systems.


.. _server:

Server
------

Job data, client information, and results are stored in a MySQL
database, either locally or on a remote system. The Autotest server
manages each client and it’s test jobs with individual “autoserv”
processes (one per client). A dispatcher process “monitor\_db”, starts
the autoserv processes to service requests based on database content.
Finally, both command-line and a web-based graphical interface is
available.


.. _client:

Client
------

The Autotest client can run either standalone or within a server
harness. It is not tightly coupled with the Autotest server, though they
are designed to work together. Primary design drivers include handling
errors implicitly, producing consistent results, ease of installation,
and maintenance simplicity.


.. _virtualization_test:

Virtualization Test
----------------------

The virtualization tests are sub-modules of the Autotest client that utilize
it's modular framework,  The entire suite of top-level autotest tests are also
available within virtualized guests. In addition, many specific sub-tests are 
provided within the virtualization sub-test framework. Some of the sub-tests 
are shared across virtualization technologies, while others are specific.

Control over the virtualization sub-tests is provided by the test-runner (script)
and/or a collection of configuration files.  The configuration file format is
highly specialized (see section cartesian_configuration_).  However, by using
the test-runner, little (if any) knowledge of the configuration file format is
required.  Utilizing the test-runner is the preferred method for individuals and
developers to execute stand-alone virtualization testing.


.. _virtualization_tests:

Virtualization Tests
=======================

.. _virtualization_tests_introduction:

Introduction
======================

The virt-test suite helps exercise virtualization features
with help from qemu, libvirt, and other related tools and facilities.
However, due to it's scope and complexity, this aspect of Autotest
has been separated into the dedicated 'virt-test' suite.  This suite
includes multiple packages dedicated to specific aspects of virtualization
testing.

Within each virt-test package, are a collection of independent sub-test
modules. These may be addressed individually or as part of a sequence.
In order to hide much of the complexity involved in virtualization
testing and development, a dedicated test-runner is included with
the virt-test suite (see section test_runner_).


.. _quickstart:

Quickstart
-----------


.. _pre-requisites:

Pre-requisites
~~~~~~~~~~~~~~~~~~~~~

#. A supported host platforms: Red Hat Enterprise Linux (RHEL) or Fedora.
   OpenSUSE should also work, but currently autotest is still
   not packaged for it, which means you have to clone autotest and put its path
   in an env variable so virt tests can find the autotest libs.
   Debian/Ubuntu now have a new experimental package that allows one to run
   the virt tests in a fairly straight forward way.

#. :doc:`Install software packages (RHEL/Fedora) <../basic/InstallPrerequesitePackages>`
#. :doc:`Install software packages (Debian/Ubuntu) <../basic/InstallPrerequesitePackagesDebian>`
#. A copy of the :doc:`virt test source <../contributing/DownloadSource>`


.. _clone:

Clone
~~~~~~~~

#. Clone the virt test repo

::

    git clone git://github.com/autotest/virt-test.git


#. Change into the repository directory

::

    cd virt-test


.. _run_bootstrap:

``./run -t <type> --bootstrap``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Where ``<type>`` is the virtualization test type you want to setup, for example
``"qemu"``.  Explicitly using ``--bootstrap`` causes setup to run interactively
and is highly recommended. Otherwise, the test runner will execute the same
operations non-interactively. Running it interactively allows for choice and
modification of to the environment to suit specific testing or setup needs.

The setup process includes checks for the minimum host software requirements and
sets up a directory tree to hold data.  It also downloads a minimal guest OS image
(about 180 MB) called JeOS (based on Fedora).  This is the default guest used
when a full-blown build from an automated install is not required.

When executed as a non-root user, ``./run -t <type> --bootstrap`` will create
and use ``$HOME/virt_test`` as the data directory to hold OS images, logs,
temporary files, etc.  Whereas for ``root``, the system-wide location
``/var/lib/virt-test`` will be used.   However it is invoked, as user, root, 
interactive, or not, a symbolic link to the data directory will be created 
``virt-test/shared/data`` (i.e. under the directory the repository was
cloned in).

Interactive ``--bootstrap`` may be run at any time, for example to re-generate
the default configuration after pulling down a new release.  Note that the
``-t <type>`` argument is crucial.  Any subdirectory of ``virt-test`` which
contains a file named ``control`` is a candidate ``<type>``. Also, each
``<type>`` has different requirements. For example, the libguestfs tests
have different software requirements than the qemu tests.

.. _run_default_tests:


Run default tests
~~~~~~~~~~~~~~~~~~~~~~


For qemu and libvirt subtests, the default test set does not require
root. However, other tests might fail due to lack of privileges.

::

    ./run -t qemu

or

::

    ./run -t libvirt


.. _run_different_tests:

Running different tests
~~~~~~~~~~~~~~~~~~~~~~~

You can list the available tests with the --list-tests parameter.

::

    $ ./run -t qemu --list-tests
    (will print a numbered list of tests, with a pagination)

Then, pass test `names` as a quote-protected, space-separated list to the --tests
parameter.  For example:

#. For qemu testing::

    $ ./run -t qemu --tests "migrate time-drift file_transfer"

#. Many libvirt tests require the ``virt-test-vm1`` guest exists, and assume it is
   removed or restored to prestine state at the end.  However, when running a
   custom set of tests this may not be the case.  In this case, you may need
   to use the ``--install`` and/or ``--remove`` options to the test runner.
   For example::

    # ./run -t libvirt --install --remove --tests "reboot"


.. _checking_results:

Checking the results
~~~~~~~~~~~~~~~~~~~~

The test runner will produce a debug log, that will be useful to debug
problems:

::

    [lmr@localhost virt-test.git]$ ./run -t qemu --tests boot_with_usb
    SETUP: PASS (1.20 s)
    DATA DIR: /path/to/virt_test
    DEBUG LOG: /path/to/virt-test.git/logs/run-2012-12-12-01.39.34/debug.log
    TESTS: 10
    boot_with_usb.ehci: PASS (18.34 s)
    boot_with_usb.keyboard.uhci: PASS (21.57 s)
    boot_with_usb.keyboard.xhci: PASS (24.56 s)
    boot_with_usb.mouse.uhci: PASS (21.59 s)
    boot_with_usb.mouse.xhci: PASS (23.11 s)
    boot_with_usb.usb_audio: PASS (20.99 s)
    boot_with_usb.hub: PASS (22.12 s)
    boot_with_usb.storage.uhci: PASS (21.61 s)
    boot_with_usb.storage.ehci: PASS (23.27 s)
    boot_with_usb.storage.xhci: PASS (25.03 s)

For convenience, the most recent debug log is pointed to by the ``logs/latest/debug.log`` symlink.

.. _utilities:

Utilities
----------

A number of helpful command-line utilities are provided along with the
Autotest client. Depending on the installation, they could be located in
various places. The table below outlines some of them along with a brief
description.

+-------------------------+------------------------------------------------------------------------------+
|  Name                   |  Description                                                                 |
+=========================+==============================================================================+
| ``autotest-local``      | The autotest command-line client.                                            |
+-------------------------+------------------------------------------------------------------------------+
| ``cartesian_config.py`` | Test matrix configuration parser module and command-line display utility.    |
+-------------------------+------------------------------------------------------------------------------+
| ``scan_results.py``     | Check for and pretty-print current testing status and/or results.            |
+-------------------------+------------------------------------------------------------------------------+
| ``html_report.py``      | Command-line HTML index and test result presentation utility.                |
+-------------------------+------------------------------------------------------------------------------+
| ``run``                 | Test runner for virt-test suite.                                             |
+-------------------------+------------------------------------------------------------------------------+

For developers, there are a separate set of utilities to help with
writing, debugging, and checking code and/or tests. Please see section
development_tools_ for more detail.


.. _test_execution:

Detailed Test Execution
========================

Tests are executed from a copy of the Autotest client code, typically on
separate hardware from the Autotest server (if there is one). Executing
tests directly from a clone of the git repositories or installed Autotest
is possible.  The tree is configured such that test results and local configuration
changes are kept separate from test and Autotest code.

For virtualization tests, variant selection(s) and configuration(s) is required either
manually through specification in tests.cfg (see section tests_cfg_) or automatically
by using the test-runner (see section run_different_tests_).  The test-runner is nearly
trivial to use, but doesn't offer the entire extent of test customization.  See the virt_test_runner
section for more information.


.. _autotest_command_line:

Autotest Command Line
----------------------

Several Autotest-client command-line options and parameters are
available. Running the ‘autotest’ command with the ‘``-h``’ or
‘``--help``’ parameters will display the online help. The only required
parameters are a path to the autotest control file which is detailed
elsewhere in the autotest documentation.


.. _output:

Output
~~~~~~~

Options for controlling client output are the most frequently used. The
client process can "in a terminal, or placed in the background.
Synchronous output via stdout/stderr is provided, however full-verbosity
logs and test results are maintained separate from the controlling
terminal. This allows users to respond to test output immediately,
and/or an automated framework (such as the autotest server) to collect
it later.


.. _verbosity:

Verbosity
~~~~~~~~~~

Access to the highest possible detail level is provided when the
‘``--verbose’`` option is used. There are multiple logging/message
levels used within autotest, from DEBUG, to INFO, and ERROR. While all
levels are logged individually, only INFO and above are displayed from
the autotest command by default. Since DEBUG is one level lower than
INFO, there are no provisions provided more granularity in terminal
output.


.. _job_names_tags:

Job Names and Tags
~~~~~~~~~~~~~~~~~~~~~

The ‘``-t``’, or ‘``--tag``’ parameter is used to specify the TAG name
that will be appended to the name of every test. JOBNAMEs come from the
autotest server, and scheduler for a particular client. When running the
autotest client stand-alone from the command line, it’s not possible to
set the JOBNAME. However, TAGs are a way of differentiating one test
execution from another within a JOB. For example, if the same test is
run multiple times with slight variations in parameters. TAGS are also a
mechanism available on the stand-alone command line to differentiate
between executions.


.. _sub_commands:

Autotest client sub-commands
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sub-commands are a shortcut method for performing various client tasks.
They are evaluated separately from the main command-line options. To use
them, simply append them after any standard parameters on the client
command line.

.. _help:

``help``
^^^^^^^^^^^^

The ``help`` sub-command prints out all sub-commands along with a short
description of their use/purpose. This help output is in addition to the
standard client command-line help output.

.. _list:

``list``
^^^^^^^^^^^^^^^^^^

The ``list`` sub-command searches for and displays a list of test names
that contain a valid control file. The list includes a short description
of each test and is sent to the default pager (i.e. more or less) for
viewing.

.. _run:

``run``
^^^^^^^^^^^^^^^

The ``run`` sub-command complements ``list``, but as a shortcut for
executing individual tests. Only the name of the test sub-directory is
needed. For example, to execute sleeptest, the
``bin/autotest-local run sleeptest`` command may be used.


.. _results:

Results
~~~~~~~~

On the client machine, results are stored in a ‘results’ sub-directory,
under the autotest client directory (AUTODIR). Within the ‘results’
sub-directory, data is grouped based on the autotest server-supplied
job-name (JOBNAME). Variant shortnames (see section variants_)
represent the <TESTNAME> value used when results are recorded.
When running a stand-alone client, or if unspecified, JOBNAME is 'default'.

+--------------------------------------------------+----------------------------------------------+
| Relative Directory or File                       | Description                                  |
+==================================================+==============================================+
| ``<AUTODIR>/results/JOBNAME/``                   | Base directory for JOBNAME(‘default’)        |
+-+------------------------------------------------+----------------------------------------------+
| | ``sysinfo``                                    | Overall OS-level data from client system     |
+-+------------------------------------------------+----------------------------------------------+
| | ``control``                                    | Copy of control file used to execute job     |
+-+------------------------------------------------+----------------------------------------------+
| | ``status``                                     | Overall results table for each TAGged test   |
+-+------------------------------------------------+----------------------------------------------+
| | ``sysinfo/``                                   | Test-centric OS-level data                   |
+-+------------------------------------------------+----------------------------------------------+
| | ``debug/``                                     | Client execution logs, See section           |
| |                                                | verbosity_.                                  |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``Client.DEBUG, client.INFO,``               | Client output at each verbosity level. Good  |
| | | ``client.WARNING, client.ERROR``             | place to start debugging any problems.       |
+-+-+----------------------------------------------+----------------------------------------------+
| | ``<TESTNAME><TAG>/``                           | Base directory of results from a specific    |
| |                                                | test                                         |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``status``                                   | Test start/end time and status report table  |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``keyval``                                   | Key / value parameters for test              |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``results/``                                 | Customized and/or nested-test results        |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``profiling/``                               | Data from profiling tools during testing     |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``debug/``                                   | Client test output at each verbosity level   |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``build<TAG>/``                              | Base directory for tests that build code     |
+-+-+-+--------------------------------------------+----------------------------------------------+
| | | | ``status``                                 | Overall build status                         |
+-+-+-+--------------------------------------------+----------------------------------------------+
| | | | ``src/``                                   | Source code used in a build                  |
+-+-+-+--------------------------------------------+----------------------------------------------+
| | | | ``build/``                                 | Compile output / build scratch directory     |
+-+-+-+--------------------------------------------+----------------------------------------------+
| | | | ``patches/``                               | Patches to apply to source code              |
+-+-+-+--------------------------------------------+----------------------------------------------+
| | | | ``config/``                                | Config. Used during & for build              |
+-+-+-+--------------------------------------------+----------------------------------------------+
| | | | ``debug/``                                 | Build output and logs                        |
+-+-+-+--------------------------------------------+----------------------------------------------+
| | | | ``summary``                                | Info. About build test/progress.             |
+-+-+-+--------------------------------------------+----------------------------------------------+


.. _test_runner:

Virt-test runner
------------------

Within the root of the virt-test sub-directory (``autotest/client/tests/virt/``,
``virt-test``, or wherever you cloned the repository) is ``run``.  This is an
executable python script which provides a single, simplified interface for running
tests. The list of available options and arguments is provided by the ``-h`` or
``--help``.

This interface also provides for initial and subsequent, interactive setup
of the various virtualization sub-test types.  Even if not, the setup will
still be executed non-interactivly before testing begins.  See the section
run_bootstrap_ for more infomration on initial setup.

To summarize it's use, execute ``./run`` with the subtest type as an argument
to ``-t`` (e.g. ``qemu``, ``libvirt``, etc.), guest operating system with
``-g`` (e.g. ``RHEL.6.5.x86_64``), and a quoted, space-separated list of
test names with ``--tests``.  Everything except ``-t <type>`` is optional.


.. _test_runner_output:

Virt-test runner output
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Assuming the ``-v`` verbose option is not used, the test runner will produce simple,
colorized pass/fail output.  Some basic statistics are provided at the end of all tests, such
as pass/fail count, and total testing time.  Full debug output is available by specifying
the ``-v`` option, or by observing ``logs/latest/debug.log``


.. _test_runner_results:

Virt-test runner results
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When utilizing the test runner, results are logged slightly different from the
autotest client.  Each run logs output and results to a date & time stamped
sub-directory beneith the ``logs/`` directory.  For convenience, there is a ``latest``
symbolic link which always points at the previous run sub-directory.  This makes it
handy for tailing a currently running test in another terminal.

+--------------------------------------------------+----------------------------------------------+
| Relative Directory or File                       | Description                                  |
+==================================================+==============================================+
| ``logs/run-YYYY-MM-DD-HH.MM.SS/``                | Results for a single run.                    |
+-+------------------------------------------------+----------------------------------------------+
| | ``debug.log``                                  | Debug-level output for entire run.           |
+-+------------------------------------------------+----------------------------------------------+
| | ``test.cartesian.short.name/``                 | Results from individual test in run          |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``debug.log``                                | Debug-level output from individual test      |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``keyval``                                   | Key / value parameters for test              |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``session-VM_NAME.log``                      | Remote ssh session log to VM_NAME guest.     |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``VM_NAME-0.webm``                           | 5-second screenshot video of VM_NAME guest   |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``results/``                                 | Customized and/or nested-test results        |
+-+-+----------------------------------------------+----------------------------------------------+
| | | ``profiling/``                               | Data from profiling tools (if configured)    |
+-+-+----------------------------------------------+----------------------------------------------+


.. _file_directory_layout:

File/Directory Layout
-----------------------

.. _file_directory_layout_overview:

Overview
~~~~~~~~~~

The autotest source tree is organized in a nested structure from server,
to client, to tests.  The final tests element is further divided between all
the independant autotest tests, and the virt test suite.  This layouy is 
intended to support easy customization at the lowest levels, while keeping
the framework, tests, and configurations separated from eachother.

Traditionally, each of these elements would be nested within eachother like so:

+------------------------+---------------------------+
| Relative directory     | Description               |
+========================+===========================+
| ``autotest/``          | Autotest server           |
+-+----------------------+---------------------------+
| | ``client/``          | Autotest client           |
+-+-+--------------------+---------------------------+
| | | ``tests/``         | Test sub-directories      |
+-+-+-+------------------+---------------------------+
| | | | ``virt/``        | virt-test subdirectories  |
+-+-+-+------------------+---------------------------+

However, for development and simple testing purposes, none of the server
components is required, and nearly all activity will occur under the client
and tests sub-directories.  Further, depending on your operating environment,
the client components may be available as the "autotest-framework" package.
When installed, work may be solely concentrated within or beneith the ``tests``
sub-directory.  For exclusivle virtualization testing, only the `virt`
sub-directory of the ``tests`` directory is required.


.. _file_directory_layout_details:

Virt-test Details
~~~~~~~~~~~~~~~~~

Traditionally the virtualization tests directory tree would be rooted at
``autotest/client/tests/virt``.  However, when utilizing the autotest-framework
package, it commonly resides under a ``virt-test`` directory,
which may be located anywhere convenient (including your home directory).

+------------------------------------------------+-----------------------------------------------+
| Relative directory                             | Description                                   |
+================================================+===============================================+
| ``run.py``                                     | The test-runner script.  (see section         |
|                                                | (test_runner_)                                |
+------------------------------------------------+-----------------------------------------------+
| ``virt.py``                                    | Module used by the autotest framework to      |
|                                                | define the ``test.test`` subclass and methods |
|                                                | needed for test execution.  This is utilized  |
|                                                | when tests are executed from the autotest     |
|                                                | client.                                       |
+------------------------------------------------+-----------------------------------------------+
| ``logs/``                                      | Logs and test results when utilizing the test |
|                                                | runner (see section test_runner_results_)     |
+------------------------------------------------+-----------------------------------------------+
| ``virttest/``                                  | Modules for host, guest, and test utilities   |
|                                                | shared by nearly all the virt-test sub-test.  |
|                                                | The scope spans multiple virtualization       |
|                                                | hypervisors, technologies, libraries and      |
|                                                | tracking facilities. Not every component is   |
|                                                | required for every test, but all              |
|                                                | virtualization tests consume multiple modules |
|                                                | within this tree.                             |
+-+----------------------------------------------+-----------------------------------------------+
| | ``common.py``                                | Central autotest framework module utilized by |
| |                                              | nearly all other modules.  It creates the     |
| |                                              | top-level namespaces under which the entirety |
| |                                              | of the autotest client framework packages are |
| |                                              | made available as                             |
| |                                              | ``autotest.client``                           |
+-+----------------------------------------------+-----------------------------------------------+
| | ``data_dir.py``                              | Provides a centralized interface for virt-test|
| |                                              | code and tests to access runtime test data    |
| |                                              | (os images, iso images, boot files, etc.)     |
+-+----------------------------------------------+-----------------------------------------------+
| | ``standalone_test.py``                       | Stand-in for the autotest-framework needed by |
| |                                              | the test runner.  Takes the place of the      |
| |                                              | ``test.test`` class.  Also provides other     |
| |                                              | test-runner specific classes and functions.   |
+-+----------------------------------------------+-----------------------------------------------+
| ``tests/``                                     | Shared virtualization sub-test modules.  The  |
|                                                | largest and most complex is the unattended    |
|                                                | install test. All test modules in this        |
|                                                | directory are virtualization technology       |
|                                                | agnostic. Most of the test modules are simple |
|                                                | and well commented. They are an excellent     |
|                                                | reference for test developers starting to     |
|                                                | write a new test.                             |
+------------------------------------------------+-----------------------------------------------+
| ``qemu``, ``libvirt``, ``libguestfs``, etc.    | Technology-specific trees organizing both     |
|                                                | test-modules and configuration.               |
+-+----------------------------------------------+-----------------------------------------------+
| | ``cfg``                                      | Runtime virt test framework and test Cartesian|
| |                                              | configuration produced by                     |
| |                                              | ``./run --bootstrap``                         |
| |                                              | and consumed by both the autotest-client and  |
| |                                              | standalone test-runner. (See section          |
| |                                              | default_configuration_files_)                 |
+-+----------------------------------------------+-----------------------------------------------+
| ``shared/``                                    | Runtime data shared amung all                 |
|                                                | virtualization tests.                         |
+-+----------------------------------------------+-----------------------------------------------+
| | ``cfg/``                                     | Persistent Cartesian configuration source for |
| |                                              | derriving technology-specific runtime         |
| |                                              | configuration and definition (See section     |
| |                                              | default_configuration_files_)                 |
+-+----------------------------------------------+-----------------------------------------------+
| | ``unattended/``                              | Data specific to the unattended install test. |
| |                                              | Kickstart, answer-files, as well as other     |
| |                                              | data utilized during the unattended install   |
| |                                              | process. Most of the files contain placeholder|
| |                                              | keywords which are substituted with actual    |
| |                                              | values at run-time                            |
+-+----------------------------------------------+-----------------------------------------------+
| | ``control/``                                 | Autotest test control files used when         |
| |                                              | executing autotest tests within a guest       |
| |                                              | virtual machine.                              |
+-+----------------------------------------------+-----------------------------------------------+
| | ``data/``                                    | A symlink to dynamic runtime data shared amung|
| |                                              | all virtualization tests.  The destination and|
| |                                              | control over this location is managed by the  |
| |                                              | ``virttest/data_dir.py`` module referenced    |
| |                                              | above.                                        |
+-+-+--------------------------------------------+-----------------------------------------------+
| | | ``boot/``                                  | Files required for starting a virtual machine |
| | |                                            | (i.e. kernel and initrd images)               |
+-+-+--------------------------------------------+-----------------------------------------------+
| | | ``images/``                                | Virtual machine disk images and related files |
+-+-+--------------------------------------------+-----------------------------------------------+
| | | ``isos/``                                  | Location for installation disc images         |
+-+-+--------------------------------------------+-----------------------------------------------+


.. _cartesian_configuration:

Cartesian Configuration
------------------------

Cartesian Configuration is a highly specialized way of providing lists
of key/value pairs within combination's of various categories. The
format simplifies and condenses highly complex multidimensional arrays
of test parameters into a flat list. The combinatorial result can be
filtered and adjusted prior to testing, with filters, dependencies, and
key/value substitutions.

The parser relies on indentation, and is very sensitive to misplacement
of tab and space characters. It’s highly recommended to edit/view
Cartesian configuration files in an editor capable of collapsing tab
characters into four space characters. Improper attention to column
spacing can drastically affect output.


.. _keys_and_values:

Keys and values
~~~~~~~~~~~~~~~~~~

Keys and values are the most basic useful facility provided by the
format. A statement in the form ``<key> = <value>`` sets ``<key>`` to
``<value>``. Values are strings, terminated by a linefeed, with
surrounding quotes completely optional (but honored). A reference of
descriptions for most keys is included in section Configuration Parameter
Reference.
The key will become part of all lower-level (i.e. further indented) variant
stanzas (see section variants_).
However, key precedence is evaluated in top-down or ‘last defined’
order. In other words, the last parsed key has precedence over earlier
definitions.


.. _variants:

Variants
~~~~~~~~~~~

A ‘variants’ stanza is opened by a ‘variants:’ statement. The contents
of the stanza must be indented further left than the ‘variants:’
statement. Each variant stanza or block defines a single dimension of
the output array. When a Cartesian configuration file contains
two variants stanzas, the output will be all possible combination's of
both variant contents. Variants may be nested within other variants,
effectively nesting arbitrarily complex arrays within the cells of
outside arrays.  For example::

    variants:
        - one:
            key1 = Hello
        - two:
            key2 = World
        - three:
    variants:
        - four:
            key3 = foo
        - five:
            key3 = bar
        - six:
            key1 = foo
            key2 = bar

While combining, the parser forms names for each outcome based on
prepending each variant onto a list. In other words, the first variant
name parsed will appear as the left most name component. These names can
become quite long, and since they contain keys to distinguishing between
results, a 'short-name' key is also used.  For example, running
``cartesian_config.py`` against the content above produces the following
combinations and names::

    dict    1:  four.one
    dict    2:  four.two
    dict    3:  four.three
    dict    4:  five.one
    dict    5:  five.two
    dict    6:  five.three
    dict    7:  six.one
    dict    8:  six.two
    dict    9:  six.three

Variant shortnames represent the <TESTNAME> value used when results are
recorded (see section Job Names and Tags. For convenience
variants who’s name begins with a ‘``@``’ do not prepend their name to
'short-name', only 'name'. This allows creating ‘shortcuts’ for
specifying multiple sets or changes to key/value pairs without changing
the results directory name. For example, this is often convenient for
providing a collection of related pre-configured tests based on a
combination of others (see section tests_).


Named variants
~~~~~~~~~~~~~~

Named variants allow assigning a parseable name to a variant set.  This enables
an entire variant set to be used for in filters_.  All output combinations will
inherit the named varient key, along with the specific variant name.  For example::

   variants var1_name:
        - one:
            key1 = Hello
        - two:
            key2 = World
        - three:
   variants var2_name:
        - one:
            key3 = Hello2
        - two:
            key4 = World2
        - three:

   only (var2_name=one).(var1_name=two)

Results in the following outcome when parsed with ``cartesian_config.py -c``::

    dict    1:  (var2_name=one).(var1_name=two)
          dep = []
          key2 = World         # variable key2 from variants var1_name and variant two.
          key3 = Hello2        # variable key3 from variants var2_name and variant one.
          name = (var2_name=one).(var1_name=two)
          shortname = (var2_name=one).(var1_name=two)
          var1_name = two      # variant name in same namespace as variables.
          var2_name = one      # variant name in same namespace as variables.

Named variants could also be used as normal variables.::

   variants guest_os:
        - fedora:
        - ubuntu:
   variants disk_interface:
        - virtio:
        - hda:

Which then results in the following::

    dict    1:  (disk_interface=virtio).(guest_os=fedora)
        dep = []
        disk_interface = virtio
        guest_os = fedora
        name = (disk_interface=virtio).(guest_os=fedora)
        shortname = (disk_interface=virtio).(guest_os=fedora)
    dict    2:  (disk_interface=virtio).(guest_os=ubuntu)
        dep = []
        disk_interface = virtio
        guest_os = ubuntu
        name = (disk_interface=virtio).(guest_os=ubuntu)
        shortname = (disk_interface=virtio).(guest_os=ubuntu)
    dict    3:  (disk_interface=hda).(guest_os=fedora)
        dep = []
        disk_interface = hda
        guest_os = fedora
        name = (disk_interface=hda).(guest_os=fedora)
        shortname = (disk_interface=hda).(guest_os=fedora)
    dict    4:  (disk_interface=hda).(guest_os=ubuntu)
        dep = []
        disk_interface = hda
        guest_os = ubuntu
        name = (disk_interface=hda).(guest_os=ubuntu)
        shortname = (disk_interface=hda).(guest_os=ubuntu)


.. _dependencies:

Dependencies
~~~~~~~~~~~~~~~

Often it is necessary to dictate relationships between variants. In this
way, the order of the resulting variant sets may be influenced. This is
accomplished by listing the names of all parents (in order) after the
child’s variant name. However, the influence of dependencies is ‘weak’,
in that any later defined, lower-level (higher indentation) definitions,
and/or filters (see section filters_) can remove or modify dependents. For
example, if testing unattended installs, each virtual machine must be booted
before, and shutdown after:

::

    variants:
        - one:
            key1 = Hello
        - two: one
            key2 = World
        - three: one two

Results in the correct sequence of variant sets: one, two, *then* three.


.. _filters:

Filters
~~~~~~~~~~

Filter statements allow modifying the resultant set of keys based on the
name of the variant set (see section variants_). Filters can be used in 3 ways:
Limiting the set to include only combination names matching a pattern.
Limiting the set to exclude all combination names not matching a
pattern. Modifying the set or contents of key/value pairs within a
matching combination name.

Names are matched by pairing a variant name component with the
character(s) ‘,’ meaning OR, ‘..’ meaning AND, and ‘.’ meaning
IMMEDIATELY-FOLLOWED-BY. When used alone, they permit modifying the list
of key/values previously defined. For example:

::

    Linux..OpenSuse:
    initrd = initrd

Modifies all variants containing ‘Linux’ followed anywhere thereafter
with ‘OpenSuse’, such that the ‘initrd’ key is created or overwritten
with the value ‘initrd’.

When a filter is preceded by the keyword ‘only’ or ‘no’, it limits the
selection of variant combination's This is used where a particular set
of one or more variant combination's should be considered selectively or
exclusively. When given an extremely large matrix of variants, the
‘only’ keyword is convenient to limit the result set to only those
matching the filter. Whereas the ‘no’ keyword could be used to remove
particular conflicting key/value sets under other variant combination
names. For example:

::

    only Linux..Fedora..64

Would reduce an arbitrarily large matrix to only those variants who’s
names contain Linux, Fedora, and 64 in them.

However, note that any of these filters may be used within named
variants as well. In this application, they are only evaluated when that
variant name is selected for inclusion (implicitly or explicitly) by a
higher-order. For example:

::

    variants:
        - one:
            key1 = Hello
    variants:
        - two:
            key2 = Complicated
        - three: one two
            key3 = World
    variants:
        - default:
            only three
            key2 =

    only default

Results in the following outcome:

::

    name = default.three.one
    key1 = Hello
    key2 =
    key3 = World


.. _value_substitutions:

Value Substitutions
~~~~~~~~~~~~~~~~~~~~~~

Value substitution allows for selectively overriding precedence and
defining part or all of a future key’s value. Using a previously defined
key, it’s value may be substituted in or as a another key’s value. The
syntax is exactly the same as in the bash shell, where as a key’s value
is substituted in wherever that key’s name appears following a ‘$’
character. When nesting a key within other non-key-name text, the name
should also be surrounded by ‘{‘, and ‘}’ characters.

Replacement is context-sensitive, thereby if a key is redefined within
the same, or, higher-order block, that value will be used for future
substitutions. If a key is referenced for substitution, but hasn’t yet
been defined, no action is taken. In other words, the $key or ${key}
string will appear literally as or within the value. Nesting of
references is not supported (i.e. key substitutions within other
substitutions.

For example, if ``one = 1, two = 2, and three = 3``; then,
``order = ${one}${two}${three}`` results in ``order = 123``. This is
particularly handy for rooting an arbitrary complex directory tree
within a predefined top-level directory.

An example of context-sensitivity,

::

    key1 = default value
    key2 = default value

    sub = "key1: ${key1}; key2: ${key2};"

    variants:
        - one:
            key1 = Hello
            sub = "key1: ${key1}; key2: ${key2};"
        - two: one
            key2 = World
            sub = "key1: ${key1}; key2: ${key2};"
        - three: one two
            sub = "key1: ${key1}; key2: ${key2};"

Results in the following,

::

    dict    1:  one
        dep = []
        key1 = Hello
        key2 = default value
        name = one
        shortname = one
        sub = key1: Hello; key2: default value;
    dict    2:  two
        dep = ['one']
        key1 = default value
        key2 = World
        name = two
        shortname = two
        sub = key1: default value; key2: World;
    dict    3:  three
        dep = ['one', 'two']
        key1 = default value
        key2 = default value
        name = three
        shortname = three
        sub = key1: default value; key2: default value;


.. _key_sub_arrays:

Key sub-arrays
~~~~~~~~~~~~~~~~~

Parameters for objects like VM’s utilize array’s of keys specific to a
particular object instance. In this way, values specific to an object
instance can be addressed. For example, a parameter ‘vms’ lists the VM
objects names to instantiate in in the current frame’s test. Values
specific to one of the named instances should be prefixed to the name:

::

    vms = vm1 second_vm another_vm
    mem = 128
    mem_vm1 = 512
    mem_second_vm = 1024

The result would be, three virtual machine objects are create. The third
one (another\_vm) receives the default ‘mem’ value of 128. The first two
receive specialized values based on their name.

The order in which these statements are written in a configuration file
is not important; statements addressing a single object always override
statements addressing all objects. Note: This is contrary to the way the
Cartesian configuration file as a whole is parsed (top-down).


.. _include_statements:

Include statements
~~~~~~~~~~~~~~~~~~~~~

The ‘``include``’ statement is utilized within a Cartesian configuration
file to better organize related content. When parsing, the contents of
any referenced files will be evaluated as soon as the parser encounters
the ``include`` statement. The order in which files are included is
relevant, and will carry through any key/value substitutions
(see section key_sub_arrays_) as if parsing a complete, flat file.


.. _combinatorial_outcome:

Combinatorial outcome
~~~~~~~~~~~~~~~~~~~~~~~~

The parser is available as both a python module and command-line tool
for examining the parsing results in a text-based listing. To utilize it
on the command-line, run the module followed by the path of the
configuration file to parse. For example,
``common_lib/cartesian_config.py tests/libvirt/tests.cfg``.

The output will be just the names of the combinatorial result set items
(see short-names, section Variants). However,
the ‘``--contents``’ parameter may be specified to examine the output in
more depth. Internally, the key/value data is stored/accessed similar to
a python dictionary instance. With the collection of dictionaries all
being part of a python list-like object. Irrespective of the internals,
running this module from the command-line is an excellent tool for both
reviewing and learning about the Cartesian Configuration format.

In general, each individual combination of the defined variants provides
the parameters for a single test. Testing proceeds in order, through
each result, passing the set of keys and values through to the harness
and test code. When examining Cartesian configuration files, it’s
helpful to consider the earliest key definitions as “defaults”, then
look to the end of the file for other top-level override to those
values. If in doubt of where to define or set a key, placing it at the
top indentation level, at the end of the file, will guarantee it is
used.


.. _formal_definition:

Formal definition
~~~~~~~~~~~~~~~~~~~~
-  A list of dictionaries is referred to as a frame.

-  The parser produces a list of dictionaries (dicts). Each dictionary
   contains a set of key-value pairs.

-  Each dict contains at least three keys: name, shortname and depend.
   The values of name and shortname are strings, and the value of depend
   is a list of strings.

-  The initial frame contains a single dict, whose name and shortname
   are empty strings, and whose depend is an empty list.

-  Parsing dict contents

   -  The dict parser operates on a frame, referred to as the current frame.

   -  A statement of the form <key> = <value> sets the value of <key> to
      <value> in all dicts of the current frame. If a dict lacks <key>,
      it will be created.

   -  A statement of the form <key> += <value> appends <value> to the
      value of <key> in all dicts of the current frame. If a dict lacks
      <key>, it will be created.

   -  A statement of the form <key> <= <value> pre-pends <value> to the
      value of <key> in all dicts of the current frame. If a dict lacks
      <key>, it will be created.

   -  A statement of the form <key> ?= <value> sets the value of <key>
      to <value>, in all dicts of the current frame, but only if <key>
      exists in the dict. The operators ?+= and ?<= are also supported.

   -  A statement of the form no <regex> removes from the current frame
      all dicts whose name field matches <regex>.

   -  A statement of the form only <regex> removes from the current
      frame all dicts whose name field does not match <regex>.

-  Content exceptions

   -  Single line exceptions have the format <regex>: <key> <operator>
      <value> where <operator> is any of the operators listed above
      (e.g. =, +=, ?<=). The statement following the regular expression
      <regex> will apply only to the dicts in the current frame whose
      name partially matches <regex> (i.e. contains a substring that
      matches <regex>).

   -  A multi-line exception block is opened by a line of the format
      <regex>:. The text following this line should be indented. The
      statements in a multi-line exception block may be assignment
      statements (such as <key> = <value>) or no or only statements.
      Nested multi-line exceptions are allowed.

-  Parsing Variants

   -  A variants block is opened by a ``variants:`` statement. The indentation
      level of the statement places the following set within the outer-most
      context-level when nested within other ``variant:`` blocks.  The contents
      of the ``variants:`` block must be further indented.

   -  A variant-name may optionally follow the ``variants`` keyword, before
      the ``:`` character.  That name will be inherited by and decorate all
      block content as the key for each variant contained in it's the
      block.

   -  The name of the variants are specified as ``- <variant\_name>:``.
      Each name is pre-pended to the name field of each dict of the variant's
      frame, along with a separator dot ('.').

   -  The contents of each variant may use the format ``<key> <op> <value>``.
      They may also contain further ``variants:`` statements.

   -  If the name of the variant is not preceeded by a @ (i.e. -
      @<variant\_name>:), it is pre-pended to the shortname field of
      each dict of the variant's frame. In other words, if a variant's
      name is preceeded by a @, it is omitted from the shortname field.

   -  Each variant in a variants block inherits a copy of the frame in
      which the variants: statement appears. The 'current frame', which
      may be modified by the dict parser, becomes this copy.

   -  The frames of the variants defined in the block are
      joined into a single frame.  The contents of frame replace the
      contents of the outer containing frame (if there is one).

-  Filters

   -  Filters can be used in 3 ways:

      -  ::

             only <filter>

      -  ::

             no <filter>

      -  ::

             <filter>: (starts a conditional block, see 4.4 Filters)

   -  Syntax:

::

    .. means AND
    . means IMMEDIATELY-FOLLOWED-BY

-  Example:

   ::

       qcow2..Fedora.14, RHEL.6..raw..boot, smp2..qcow2..migrate..ide

::

    means match all dicts whose names have:
    (qcow2 AND (Fedora IMMEDIATELY-FOLLOWED-BY 14)) OR
    ((RHEL IMMEDIATELY-FOLLOWED-BY 6) AND raw AND boot) OR
    (smp2 AND qcow2 AND migrate AND ide)

-  Note:

   ::

       'qcow2..Fedora.14' is equivalent to 'Fedora.14..qcow2'.

::

    'qcow2..Fedora.14' is not equivalent to 'qcow2..14.Fedora'.
    'ide, scsi' is equivalent to 'scsi, ide'.


.. _examples_cartesian:

Examples
~~~~~~~~~~~~

-  A single dictionary::

    key1 = value1
    key2 = value2
    key3 = value3

    Results in the following::

    Dictionary #0:
        depend = []
        key1 = value1
        key2 = value2
        key3 = value3
        name =
        shortname =

-  Adding a variants block::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
        - two:
        - three:

   Results in the following::

    Dictionary #0:
        depend = []
        key1 = value1
        key2 = value2
        key3 = value3
        name = one
        shortname = one
    Dictionary #1:
        depend = []
        key1 = value1
        key2 = value2
        key3 = value3
        name = two
        shortname = two
    Dictionary #2:
        depend = []
        key1 = value1
        key2 = value2
        key3 = value3
        name = three
        shortname = three

-  Modifying dictionaries inside a variant::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
            key1 = Hello World
            key2 <= some_prefix_
        - two:
            key2 <= another_prefix_
        - three:

   Results in the following::

    Dictionary #0:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = one
        shortname = one
    Dictionary #1:
        depend = []
        key1 = value1
        key2 = another_prefix_value2
        key3 = value3
        name = two
        shortname = two
    Dictionary #2:
        depend = []
        key1 = value1
        key2 = value2
        key3 = value3
        name = three
        shortname = three

-  Adding dependencies::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
            key1 = Hello World
            key2 <= some_prefix_
        - two: one
            key2 <= another_prefix_
        - three: one two

   Results in the following::

    Dictionary #0:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = one
        shortname = one
    Dictionary #1:
        depend = ['one']
        key1 = value1
        key2 = another_prefix_value2
        key3 = value3
        name = two
        shortname = two
    Dictionary #2:
        depend = ['one', 'two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = three
        shortname = three

-  Multiple variant blocks::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
            key1 = Hello World
            key2 <= some_prefix_
        - two: one
            key2 <= another_prefix_
        - three: one two

    variants:
        - A:
        - B:

   Results in the following::

    Dictionary #0:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = A.one
        shortname = A.one
    Dictionary #1:
        depend = ['A.one']
        key1 = value1
        key2 = another_prefix_value2
        key3 = value3
        name = A.two
        shortname = A.two
    Dictionary #2:
        depend = ['A.one', 'A.two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = A.three
        shortname = A.three
    Dictionary #3:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = B.one
        shortname = B.one
    Dictionary #4:
        depend = ['B.one']
        key1 = value1
        key2 = another_prefix_value2
        key3 = value3
        name = B.two
        shortname = B.two
    Dictionary #5:
        depend = ['B.one', 'B.two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = B.three
        shortname = B.three

-  Filters, ``no`` and ``only``::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
            key1 = Hello World
            key2 <= some_prefix_
        - two: one
            key2 <= another_prefix_
        - three: one two

    variants:
        - A:
            no one
        - B:
            only one,three

   Results in the following::

    Dictionary #0:
        depend = ['A.one']
        key1 = value1
        key2 = another_prefix_value2
        key3 = value3
        name = A.two
        shortname = A.two
    Dictionary #1:
        depend = ['A.one', 'A.two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = A.three
        shortname = A.three
    Dictionary #2:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = B.one
        shortname = B.one
    Dictionary #3:
        depend = ['B.one', 'B.two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = B.three
        shortname = B.three

-  Short-names::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
            key1 = Hello World
            key2 <= some_prefix_
        - two: one
            key2 <= another_prefix_
        - three: one two

    variants:
        - @A:
            no one
        - B:
            only one,three

   Results in the following::

    Dictionary #0:
        depend = ['A.one']
        key1 = value1
        key2 = another_prefix_value2
        key3 = value3
        name = A.two
        shortname = two
    Dictionary #1:
        depend = ['A.one', 'A.two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = A.three
        shortname = three
    Dictionary #2:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = B.one
        shortname = B.one
    Dictionary #3:
        depend = ['B.one', 'B.two']
        key1 = value1
        key2 = value2
        key3 = value3
        name = B.three
        shortname = B.three

-  Exceptions::

    key1 = value1
    key2 = value2
    key3 = value3

    variants:
        - one:
            key1 = Hello World
            key2 <= some_prefix_
        - two: one
            key2 <= another_prefix_
        - three: one two

    variants:
        - @A:
            no one
        - B:
            only one,three

    three: key4 = some_value

    A:
        no two
        key5 = yet_another_value

   Results in the following::

    Dictionary #0:
        depend = ['A.one', 'A.two']
        key1 = value1
        key2 = value2
        key3 = value3
        key4 = some_value
        key5 = yet_another_value
        name = A.three
        shortname = three
    Dictionary #1:
        depend = []
        key1 = Hello World
        key2 = some_prefix_value2
        key3 = value3
        name = B.one
        shortname = B.one
    Dictionary #2:
        depend = ['B.one', 'B.two']
        key1 = value1
        key2 = value2
        key3 = value3
        key4 = some_value
        name = B.three
        shortname = B.three


.. _default_configuration_files:

Default Configuration Files
----------------------------

The test configuration files are used for controlling the framework, by
specifying parameters for each test. The parser produces a list of
key/value sets, each set pertaining to a single test. Variants are
organized into separate files based on scope and/or applicability. For
example, the definitions for guest operating systems is sourced from a
shared location since all virtualization tests may utilize them.

For each set/test, keys are interpreted by the test dispatching system,
the pre-processor, the test module itself, then by the post-processor.
Some parameters are required by specific sections and others are
optional. When required, parameters are often commented with possible
values and/or their effect. There are select places in the code where
in-memory keys are modified, however this practice is discouraged unless
there’s a very good reason.

When ``./run --bootstrap`` executed (see section run_bootstrap_), copies of the
sample configuration files are copied for use under the ``cfg`` subdirectory of
the virtualization technology-specific directory.  For example, ``qemu/cfg/base.cfg``.
These copies are the versions used by the framework for both the autotest client
and test-runner.

+-----------------------------+-------------------------------------------------+
| Relative Directory or File  | Description                                     |
+-----------------------------+-------------------------------------------------+
| cfg/tests.cfg               | The first file read that includes all other     |
|                             | files, then the master set of filters to select |
|                             | the actual test set to be run.  Normally        |
|                             | this file never needs to be modified unless     |
|                             | precise control over the test-set is needed     |
|                             | when utilizing the autotest-client (only).      |
+-----------------------------+-------------------------------------------------+
| cfg/tests-shared.cfg        | Included by ``tests.cfg`` to indirectly         |
|                             | reference the remaining set of files to include |
|                             | as well as set some global parameters.          |
|                             | It is used to allow customization and/or        |
|                             | insertion within the set of includes. Normally  |
|                             | this file never needs to be modified.           |
+-----------------------------+-------------------------------------------------+
| cfg/base.cfg                | Top-level file containing important parameters  |
|                             | relating to all tests.  All keys/values defined |
|                             | here will be inherited by every variant unless  |
|                             | overridden.  This is the *first* file to check  |
|                             | for settings to change based on your environment|
+-----------------------------+-------------------------------------------------+
| cfg/build.cfg               | Configuration specific to pre-test code         |
|                             | compilation where required/requested. Ignored   |
|                             | when a client is not setup for build testing.   |
+-----------------------------+-------------------------------------------------+
| cfg/subtests.cfg            | Automatically generated based on the test       |
|                             | modules and test configuration files found      |
|                             | when the ``./run --bootstrap`` is used.         |
|                             | Modifications are discourraged since they will  |
|                             | be lost next time ``--bootstrap`` is used.      |
+-----------------------------+-------------------------------------------------+
| cfg/guest-os.cfg            | Automatically generated from                    |
|                             | files within ``shared/cfg/guest-os/``.  Defines |
|                             | all supported guest operating system            |
|                             | types, architectures, installation images,      |
|                             | parameters, and disk device or image names.     |
+-----------------------------+-------------------------------------------------+
| cfg/guest-hw.cfg            | All virtual and physical hardware related       |
|                             | parameters are organized within variant names.  |
|                             | Within subtest variants or the top-level test   |
|                             | set definition, hardware is specified by        |
|                             | Including, excluding, or filtering variants and |
|                             | keys established in this file.                  |
+-----------------------------+-------------------------------------------------+
| cfg/cdkeys.cfg              | Certain operating systems require non-public    |
|                             | information in order to operate and or install  |
|                             | properly. For example, installation numbers and |
|                             | license keys. None of the values in this file   |
|                             | are populated automatically. This file should   |
|                             | be edited to supply this data for use by the    |
|                             | unattended install test.                        |
+-----------------------------+-------------------------------------------------+
| cfg/virtio-win.cfg          | Paravirtualized hardware when specified for     |
|                             | Windows testing, must have dependent drivers    |
|                             | installed as part of the OS installation        |
|                             | process. This file contains mandatory variants  |
|                             | and keys for each Windows OS version,           |
|                             | specifying the host location and installation   |
|                             | method for each driver.                         |
+-----------------------------+-------------------------------------------------+


.. _configuration_file_details:

Configuration file details
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. _base_cfg:

Base
^^^^^^^^^

Nearly as important as tests.cfg, since it's the first file processed.
This file is responsible for defining all of the top-level default
settings inherited by all hardware, software, subtest, and run-time
short-name variants. It's critical for establishing the default
networking model of the host system, pathnames, and the virtualization
technology being tested. It also contains guest options that don't fit
within the context of the other configuration files, such as default
memory size, console video creation for tests, and guest console display
options (for human monitoring). When getting started in virtualization
autotest, or setting up on a new host, this is usually the file to edit
first.

.. _tests_cfg:

tests
^^^^^^^^^^^^

The ``tests.cfg`` file is responsible for acting on the complete
collection of variants available and producing a useful result.
In other words, all other configuration files (more or less)
define “what is possible”, ``tests.cfg`` defines what will
actually happen.

In the order they appear, there are three essential sections:

-  A set of pre-configured example short-name variants for several OS's,
   hypervisor types, and virtual hardware configurations. They can be
   used directly, and/or copied and modified as needed.

-  An overriding value-filter set, which adjusts several key path-names
   and file locations that are widely applicable.

-  The final top-level scoping filter set for limiting the tests to run,
   among the many available.

The default configuration aims to support the quick-start (see section run_)
with a simple and minimal test set that's easy to get running. It calls on
a variant defined within the pre-configured example set as described above. It
also provides the best starting place for exploring the configuration format
and learning about how it's used to support virtualization testing.


.. _cdkeys_virtio_cfg:

cdkeys and windows virtio
^^^^^^^^^^^^^^^^^^^^^^^^^^

This is the least-accessed among the configuration files. It exists
because certain operating systems require non-public information in
order to operate and or install properly. Keeping this data stored in a
special purpose file, keeps the data allows it's privacy level to be
controlled. None of the values in this file are populated automatically.
This file should be hand-edited to supply this data for use by the
autotest client. It is not required for the default test configured in
``tests.cfg.``

The windows-centric ``virtio-win.cfg`` file is similar in that it is
only applicable to windows guest operating systems. It supplements
windows definitions from ``guest-os.cfg`` with configuration needed to
ensure the virtio drivers are available during windows installation.

To install the virtio drivers during guest install, virtualization
autotest has to inform the windows install programs \*where\* to find
the drivers. Virtualization autotest uses a boot floppy with a Windows
answer file in order to perform unattended install of windows guests.
For winXP and win2003, the unattended files are simple ``.ini`` files,
while for win2008 and later, the unattended files are XML files.
Therefor, it makes the following assumptions:

-  An iso file is available that contains windows virtio drivers (inf
   files) for both netkvm and viostor.

-  For WinXP or Win2003, a a pre-made floppy disk image is available
   with the virtio drivers and a configuration file the Windows
   installer will read, to fetch the right drivers.

-  Comfort and familiarity editing and working with the Cartesian
   configuration file format, setting key values and using filters to
   point virtualization autotest at host files.


.. _guest_hw_os:

guest hw & guest os
^^^^^^^^^^^^^^^^^^^^^^

Two of the largest and most complex among the configuration files, this
pair defines a vast number of variants and keys relating purely to guest
operating system parameters and virtual hardware. Their intended use is
from within ``tests.cfg`` (see section tests_). Within ``tests.cfg`` short-name
variants, filters are used for both OS and HW variants in these files to
choose among the many available sets of options.

For example if a test requires the virtio network driver is used, it
would be selected with the filter '``only virtio_net``'. This filter
means content of the virtio\_net variant is included from
``guest-hw.cfg``, which in turn results in the '``nic_model = virtio``'
definition. In a similar manner, all guest installation methods (with
the exception of virtio for Windows) and operating system related
parameters are set in ``guest-os.cfg``.


.. _sub_tests_cfg:

Sub-tests
^^^^^^^^^^^

The third most complex of the configurations, ``subtests.cfg`` holds
variants defining all of the available virtualization sub-tests
available. They include definitions for running nested
non-virtualization autotest tests within guests. For example, the
simplistic 'sleeptest' may be run with the filter
'``only autotest.sleeptest``'.

The ``subtests.cfg`` file is rarely edited directly, instead it's
intended to provide a reasonable set of defaults for testing. If
particular test keys need customization, this should be done within the
short-name variants defined or created in ``tests.cfg`` (see section tests_).
However, available tests and their options are commented within
``subtests.cfg``, so it is often referred to as a source for available tests
and their associated controls.

.. _config_usage_details:

Configuration usage details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. _default_test_set:

For a complete reference, refer to
:doc:`the cartesian config params documentation <../advanced/cartesian/CartesianConfigParametersIntro>`


.. _preserving_installed_guest_images:

Preserving installed Guest images
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

See :doc:`Run tests on an existing guest <../advanced/RunTestsExistingGuest>`


.. _specialized_networking:

Specialized Networking
^^^^^^^^^^^^^^^^^^^^^^^^

See :doc:`Autotest networking documentation <Networking>`


.. _using_virtio_drivers_windows:

Using virtio drivers with windows
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Required items include access to the virtio driver installation image,
the Windows ISO files, and the ``winutils.iso`` CD (See section
run_bootstrap_) . Every effort is made to standardize on files
available from MSDN. For example, using the Windows7 64 bit
(non SP1) requires the CD matching:

-  ::

       cdrom_cd1 = isos/windows/en_windows_7_ultimate_x86_dvd_x15-65921.iso

-  ::

       sha1sum_cd1 = 5395dc4b38f7bdb1e005ff414deedfdb16dbf610

This file can be downloaded from the MSDN site then it’s ``SHA1``
verified.

Next, place the windows media image (creating directory if needed) in
``shared/data/isos/windows/``. Edit the ``cfg/cdkeys.cfg`` file to supply
license information if required.

Finally, if not using the test runner, set up ``cfg/tests.cfg`` to include the
``windows_quick`` short-name variant (see section tests_). Modify the
network and block device filters to use '``virtio_net``' and '``virtio-blk``'
instead.


.. _development_tools:

Development tools / utilities
--------------------------------

A number of utilities are available for the autotest core, client,
and/or test developers.  Depending on your installation type, these may be
located in different sub-directories of the tree.

+-------------------------------------------+--------------------------------------------------+
| Name                                      | Description                                      |
+===========================================+==================================================+
| ``run_pylint.py``                         | Wrapper is required to run pylint due to the     |
|                                           | way imports have been implemented.               |
+-------------------------------------------+--------------------------------------------------+
| ``check_patch.py``                        | Help developers scan code tree and display or fix|
|                                           | problems                                         |
+-------------------------------------------+--------------------------------------------------+
| ``reindent.py``                           | Help developers fix simple indentation           |
|                                           | problems                                         |
+-------------------------------------------+--------------------------------------------------+


Contributions
---------------


.. _code_contributions:

Code
~~~~~~~~

Contributions of additional tests and code are always welcome. If in
doubt, and/or for advice on approaching a particular problem, please
contact the projects members (see section _collaboration) Before submitting code,
please review the `git repository configuration guidelines <http://github.com/autotest/autotest/wiki/GitWorkflow>`_.

To submit changes, please follow `these instructions <https://github.com/autotest/autotest/wiki/SubmissionChecklist>`_.
Please allow up to two weeks for a maintainer to pick
up and review your changes.  Though, if you'd like help at any stage, feel free to post on the mailing
lists and reference your pull request.

.. _docs_contribution:

Docs
~~~~~~~~

Please edit the documentation directly to correct any minor inaccuracies
or to clarify items. The preferred markup syntax is
`ReStructuredText <http://en.wikipedia.org/wiki/ReStructuredText>`_,
keeping with the conventions and style found in existing documentation.
For any graphics or diagrams, web-friendly formats should be used, such as
PNG or SVG.

Avoid using 'you', 'we', 'they', as they can be ambiguous in reference
documentation.  It works fine in conversation and e-mail, but looks weird
in reference material. Similarly, avoid using 'unnecessary', off-topic, or
extra language. For example in American English, `"Rinse and repeat" 
<http://en.wikipedia.org/wiki/Lather,_rinse,_repeat>`_ is a funny phrase,
but could cause problems when translated into other languages. Basically,
try to avoid anything that slows the reader down from finding facts.

For major documentation work, it’s more convenient to use a different
approach. The autotest wiki is stored on github as a separate repository
from the project code. The wiki repository contains all the files, and
allows for version control over them. To clone the wiki repository, click
the ``Clone URL`` button on the wiki page (next to ``Page History``.

When working with the wiki repository, it’s sometimes convenient to
render the wiki pages locally while making and committing changes. The
gollum ruby gem may be installed so you can view the wiki locally.
See `the gollum wiki readme <https://github.com/github/gollum#readme>`_ for
more details.

_contact_info:

Contact Info.
~~~~~~~~~~~~~

`Please refer to this page <https://github.com/autotest/autotest/wiki/ContactInfo>`_