.. _multi_vm_testing:

===========================================
Multi-VM, Stateful, and Graph-Based Testing
===========================================

Avocado-VT can expand one Cartesian test definition into tests involving
multiple virtual machines and networks. It can also preserve object states
between tests and schedule dependent tests as a graph so that expensive setup
is reused.

These features were originally developed by the Avocado I2N project and are
now part of Avocado-VT. They are optional: ordinary Avocado-VT tests continue
to use the standard resolver and nrunner unless the corresponding command-line
options are selected.

The examples below use the ``tp_multivm`` sample suite shipped with
Avocado-VT. Its ``configs``, ``tests``, ``controls``, ``data``, ``tools``, and
``utils`` directories provide a working reference for writing a multi-VM test
suite.


Motivation
==========

Consider a test that opens a dialog and then validates many independent paths
through it. Repeating the complete setup for every path is wasteful, while
putting all paths in one long test makes them harder to isolate and lets one
path affect another.

A stateful test graph offers a third option. The common steps form a setup
test which saves the resulting object state. Each independent test starts
from that checkpoint and validates only its own path. Tests remain small and
isolated while the expensive setup is performed once and reused.

The model has two complementary goals:

* **test thoroughness** -- Cartesian configuration generates many scenarios
  from a compact set of parameters and reusable test code;
* **execution reuse** -- saved states and dependency-aware scheduling avoid
  repeating common setup.

See :doc:`CartesianConfig` for the Cartesian configuration language itself.
This chapter describes how the resulting variants become multi-object tests
and, optionally, a stateful dependency graph.


Execution model
===============

Test objects and states
-----------------------

A test object is a stateful resource used by a test. The sample suite models
images, virtual machines, and VM networks:

* an image state stores the persistent disks of a VM;
* a VM state combines its image state with a running-machine state;
* a network state represents the coordinated state of a group of VMs and its
  network configuration.

State transitions form a tree for each object. The root represents creation
of the object and deeper nodes represent progressively prepared states. A
test may require states provided by earlier tests and may provide new states
for later tests.

The available backends have different trade-offs. QCOW2 snapshots are easy
to copy and share. LVM can be fast, particularly when backed by RAM, but is
less portable and requires careful cleanup. A running-VM backend avoids a
boot when restoring a VM, while an image backend is usually more suitable for
multi-disk layouts. Not every backend supports every device type or storage
layout, so select one according to the suite and host environment.

An externally managed or manually prepared VM can also be represented as a
permanent VM. Its known starting states become roots from which Avocado-VT
may create disposable test states without modifying the original setup.


Building and traversing the graph
---------------------------------

The graph is constructed and run in three broad stages:

1. **Parse test and object variants.**  Cartesian configuration produces test
   nodes together with the VM, image, and network objects they use and the
   states they require or provide.
2. **Connect dependencies.**  A required state links a test to the test that
   provides it. Tests can have several parents or children when multiple
   objects participate in a scenario.
3. **Schedule useful paths.**  The traverser follows dependencies and tries to
   keep reusable setup available while it runs the selected leaf tests. A
   failed prerequisite can therefore prevent dependent tests from running.

Keeping dependency trees simple gives the traverser the best opportunity to
reuse setup. Reuse cannot be guaranteed when dependencies conflict, state
storage is limited, or a state is deliberately short-lived.


Choosing the run mode
=====================

The multi-VM parser, state hooks, and graph traverser are separate choices:

``--vt-multi-vm``
    Expand a VT test with all selected VM and network objects. Without an
    alternative suite runner, the resulting tests are executed by Avocado's
    normal nrunner.

``--vt-states``
    Enable image, VM, and network state lifecycle hooks. This option applies
    to ``avocado run`` and is meaningful together with ``--vt-multi-vm``.

``--suite-runner traverser``
    Construct the dependency graph and schedule it with Avocado-VT's graph
    traverser instead of the normal suite runner.

For example, list expanded tests and make a stateless dry run with::

    avocado list --vt-multi-vm "only=tutorial3"
    avocado run --vt-multi-vm "only=tutorial3" --dry-run

to see the following output::

    avocado-vt normal.nongui.tutorial3.no_remote.vms.vm1.qemu_kvm_centos.default_bios.virtio_rng.rng_random.no_9p_export.smallpages.no_pci_assignable.qcow2.virtio_blk.smp2.virtio_net.i440fx.Linux.CentOS.8.0.x86_64.nets.localhost.net1.vm2.qemu_kvm_windows_10.default_bios.no_virtio_rng.no_9p_export.smallpages.no_pci_assignable.qcow2.virtio_blk.smp2.virtio_net.q35.Windows.Win10.x86_64.nets.localhost.net1
    JOB ID     : 0000000000000000000000000000000000000000
    JOB LOG    : /var/tmp/avocado-dry-run-xscsqhbd/job-2026-09-04T19.11-0000000/job.log
    (1/1) normal.nongui.tutorial3.no_remote.vms.vm1.qemu_kvm_centos.default_bios.virtio_rng.rng_random.no_9p_export.smallpages.no_pci_assignable.qcow2.virtio_blk.smp2.virtio_net.i440fx.Linux.CentOS.8.0.x86_64.nets.localhost.net1.vm2.qemu_kvm_windows_10.default_bios.no_virtio_rng.no_9p_export.smallpages.no_pci_assignable.qcow2.virtio_blk.smp2.virtio_net.q35.Windows.Win10.x86_64.nets.localhost.net1: STARTED
    (1/1) normal.nongui.tutorial3.no_remote.vms.vm1.qemu_kvm_centos.default_bios.virtio_rng.rng_random.no_9p_export.smallpages.no_pci_assignable.qcow2.virtio_blk.smp2.virtio_net.i440fx.Linux.CentOS.8.0.x86_64.nets.localhost.net1.vm2.qemu_kvm_windows_10.default_bios.no_virtio_rng.no_9p_export.smallpages.no_pci_assignable.qcow2.virtio_blk.smp2.virtio_net.q35.Windows.Win10.x86_64.nets.localhost.net1: CANCEL: Test cancelled due to --dry-run (0.00 s)
    RESULTS    : PASS 0 | ERROR 0 | FAIL 0 | SKIP 0 | WARN 0 | INTERRUPT 0 | CANCEL 1
    JOB HTML   : /var/tmp/avocado-dry-run-xscsqhbd/job-2026-09-04T19.11-0000000/results.html
    JOB TIME   : 1.09 s

Enable both state handling and dependency traversal with::

    avocado run --vt-multi-vm --vt-states --suite-runner traverser \
        "only=tutorial3 dry_run=yes"

and you should see the output::

    JOB ID     : 90890c45770d9439bc8e64a55a1629dcc10a31bf
    JOB LOG    : /root/avocado/job-results/job-2026-09-04T19.11-90890c4/job.log
    RESULTS    : PASS 0 | ERROR 0 | FAIL 0 | SKIP 1 | WARN 0 | INTERRUPT 0 | CANCEL 0
    JOB HTML   : /root/avocado/job-results/job-2026-09-04T19.11-90890c4/results.html
    JOB TIME   : 6.59 s

Only one test reference is accepted for a multi-VM run because that reference
expands into multiple graph-generated test nodes. Extra ``KEY=VALUE`` parameters
may be placed in the reference string, as in the examples above.


Configuring a suite
-------------------

Set ``suite_path`` in the ``[vt.common]`` section of an Avocado configuration
file. An installed package defaults to the bundled ``tp_multivm`` suite::

    [vt.common]
    suite_path = /usr/share/avocado-plugins-vt/tp_multivm/

A compatible suite normally contains:

``configs``
    Cartesian definitions for test sets, object variants, and defaults.

``tests``
    The test implementations.

``controls``
    Optional control files run on hosts or guests.

``utils`` and ``tools``
    Reusable suite code and optional environment-tool extensions.

``data``
    Optional files consumed or deployed by tests.

The sample suite uses ``sets.cfg`` to define final test selections and object
configuration files to define available VM variants. Its override files show
where installation-specific paths and default selections can be supplied.


Environment tools
=================

The ``avocado env`` command runs stateful environment operations directly.
It uses the graph traverser and state handling internally, and accepts
Cartesian ``KEY=VALUE`` parameters as positional arguments. For example::

    avocado env setup=update vms=vm1
    avocado env setup=get get_state=customize vms=vm1

The ``setup`` parameter can contain a comma-separated chain. Steps execute in
the order given::

    avocado env setup=update,boot,run only=all

If ``setup`` is omitted, the suite's configured default is used. The bundled
sample suite defaults to ``run``.

Core environment steps include:

* ``noop``, ``list``, ``run``, and ``unittest`` for inspection and execution;
* ``start`` and ``stop`` for configured workers;
* ``create``, ``collect``, ``boot``, ``shutdown``, ``clean``, and ``update``
  for VM and object lifecycle operations;
* ``check``, ``get``, ``set``, ``unset``, ``push``, and ``pop`` for states;
* ``upload``, ``download``, and ``control`` for data and control-file
  operations.

Suites may expose compatible custom tools in addition to these core steps.


State policies
--------------

The ``get_mode``, ``set_mode``, and ``unset_mode`` parameters control how a
state operation responds to an existing or missing state. Each value contains
two characters: the first selects the action when the state exists and the
second selects the action when it does not.

The available action letters are:

``a``
    Abort the operation.

``r``
    Reuse the existing state or retain it during cleanup.

``i``
    Ignore the state and continue without the operation.

``f``
    Force creation, replacement, or removal, depending on the operation.

The valid combinations are:

.. list-table::
   :header-rows: 1

   * - Parameter
     - Existing state
     - Missing state
   * - ``get_mode``
     - ``a``, ``r``, or ``i``
     - ``a`` or ``i``
   * - ``set_mode``
     - ``a``, ``r``, or ``f``
     - ``a`` or ``f``
   * - ``unset_mode``
     - ``r`` or ``f``
     - ``a`` or ``i``

For example, ``get_mode=ra`` reuses an existing state but aborts when it is
missing. ``set_mode=ff`` overwrites an existing state and creates a missing
one. Policies may also be specialized for a VM or image with parameters such
as ``get_mode_images_vm1``.

The state operation parameters follow the same suffixing rules. Common forms
include ``get_state``, ``set_state``, and ``unset_state``, together with
object-specific forms such as ``get_state_images`` and
``set_state_vms_vm1``.


Selecting tests and objects
===========================

Test restrictions
-----------------

The ``only`` and ``no`` parameters filter Cartesian variant names. Within a
restriction:

* ``.`` means immediately followed by;
* ``..`` means AND;
* ``,`` means OR.

Repeated ``only`` parameters also combine with AND. These two commands are
therefore equivalent::

    avocado env only=aaa only=bbb
    avocado env only=aaa..bbb

Examples using the selections from the sample suite include::

    avocado env only=minimal only=tutorial1
    avocado env only=normal..tutorial2 only=names,files
    avocado env only=tutorial2..names,quicktest.tutorial2.files

Selections such as ``all``, ``nonleaves``, ``leaves``, ``normal``, and
``minimal`` are suite-defined conveniences rather than built-in Avocado
keywords. The sample ``sets.cfg`` defines them and ``default_only`` selects
which one is used when the command line supplies none.


Object restrictions
-------------------

Use ``only_<object>`` to restrict an object's Cartesian variants. For VM
objects this commonly appears as ``only_vm1``, ``only_vm2``, and so on::

    avocado env only_vm2=Win10
    avocado env only_vm1=CentOS only=tutorial1
    avocado env only_vm2=

An empty restriction allows every compatible variant. The ``vms`` parameter
instead selects which already-defined VM objects an environment operation
acts on::

    avocado env setup=clean vms=vm2

Parameters can be specialized for one object by appending its suffix. For
example, ``nic_vm2`` applies ``nic`` only to ``vm2``.


Setup reuse example
-------------------

The following sequence prepares two VMs, runs a test, removes one VM, and runs
the test again::

    avocado env setup=update vms=vm1,vm2
    avocado env only=tutorial2..files
    avocado env setup=clean vms=vm1
    avocado env only=tutorial2..files

If the selected test requires a state of ``vm1``, the final command traverses
the graph from the missing VM root through only the setup nodes needed to
provide that state. Existing unrelated setup for ``vm2`` can remain
available. This is the central benefit of combining object states with graph
dependencies.


Debugging and maintenance
=========================

Stateful runs keep VM state available across test boundaries. This makes it
possible to inspect a VM after a failure or restore a named state explicitly::

    avocado env setup=get get_state=customize vms=vm1

Some tests or backends still shut down a VM as part of their normal behavior,
for example when saving an image state. Do not assume that every failed test
leaves a live VM.

The traverser can write graphical representations of the parsed and executed
graph into the job results directory. The ``cartgraph_verbose_level``
parameter controls detailed graph output; setting it to ``0`` enables the most
verbose form in the bundled integration tests.

Suite utilities can have colocated unit tests named ``*_unittest.py``. Run
all discovered utility and tool tests, or restrict their filenames, with::

    avocado env setup=unittest
    avocado env setup=unittest 'ut_filter=*_helper_unittest.py'


Running an individual graph node
--------------------------------

The ``run`` environment step can execute an internal node without automatic
state preparation::

    avocado env setup=run only=all..set_provider vms=vm1

This is useful for manual debugging, but the caller is responsible for
providing the node's prerequisites and for any required cleanup. Normal
traversed runs should select reachable leaf tests and let the graph supply
their dependencies.


Developing multi-VM tests
=========================

Start with the :doc:`WritingTests/index` guide for the normal Avocado-VT test
structure and with :doc:`CartesianConfig` for configuration syntax. Then use
the bundled ``tp_multivm`` suite as the reference for:

* declaring VM and network objects;
* expressing required and provided states;
* separating internal setup nodes from leaf use cases;
* writing multi-VM tests and reusable suite utilities; and
* adding environment tools and controls.

The implementation lives primarily in ``virttest.cartgraph``,
``virttest.states``, ``virttest.vmnet``, and ``virttest.intertest_setup``.
Their generated module documentation is available from the API Reference.
