
Virt test source structure
==========================

When starting to contribute to a project, a high level description of the
directory structure is frequently useful. In virt-tests, at the time of
this writing (01-09-2013), the output of the command `tree` for this structure
looks like:

::

    .
    |-- libvirt
    |   |-- cfg
    |   `-- tests
    |       `-- cfg
    |-- openvswitch
    |   |-- cfg
    |   `-- tests
    |       `-- cfg
    |-- qemu
    |   |-- cfg
    |   `-- tests
    |       `-- cfg
    |-- shared
    |   |-- autoit
    |   |-- blkdebug
    |   |-- cfg
    |   |   `-- guest-os
    |   |       |-- Linux
    |   |       |   |-- Fedora
    |   |       |   |-- JeOS
    |   |       |   |-- LinuxCustom
    |   |       |   |-- OpenSUSE
    |   |       |   |-- RHEL
    |   |       |   |-- SLES
    |   |       |   `-- Ubuntu
    |   |       `-- Windows
    |   |           |-- Win2000
    |   |           |-- Win2003
    |   |           |-- Win2008
    |   |           |-- Win7
    |   |           |-- WindowsCustom
    |   |           |-- WinVista
    |   |           `-- WinXP
    |   |-- control
    |   |-- deps
    |   |   |-- test_clock_getres
    |   |   `-- test_cpu_flags
    |   |-- download.d
    |   |-- scripts
    |   |-- steps
    |   `-- unattended
    |-- tests
    |   `-- cfg
    |-- tools
    |-- v2v
    |   |-- cfg
    |   `-- tests
    |       `-- cfg
    `-- virttest


Talking about the top level directories:

Subtest dirs
------------

Those directories hold specific test code for different virtualization types.
Originally, virt-tests started as a set of tests for kvm, project that was
known as virt-test. The request to support other virt backends, such as
libvirt made us to generalize the tests infrastructure and support other
backends. As of the timeof this writing, we have 4 main backends, which we
expect to grow:

1) qemu (used to be known as kvm)
2) libvirt
3) openvswitch (bridge technology testing)
4) v2v (testing of tools used to migrate vms from 1 technlogy to another)

Inside a subtest dir, the structure is, usually:

::

    |-- qemu
    |   |-- cfg -> Config files that will be parsed by the test runner/autotest
    |   `-- tests -> Holds the tests specific to that backend
    |       `-- cfg -> Holds config snippets for the tests

The test runner, for example, will parse the top level config file
``qemu/cfg/tests.cfg``. This file includes a number of other files, and will
generate a large set of dictionaries, with all variations of a given set of
parameters.

Not all virt tests require config snippets, but some might want to make use of
the features of the [CartesianConfigReference | Cartesian files] and make one
test source to generate several different tests. If you don't want to use that,
no sweat, you're not obligated.

The snippets in tests/cfg will be used to generate subtests.cfg, a listing of
all tests available for that particular backend.

Shared tests
------------

Some tests in virt-tests are generic enough that they might run in more than one
virt backend. For example, if one virt test uses guests, but does not use the
qemu monitor interface (vm.monitor), it's likely that it belongs to the shared
test dir (toplevel tests). The structure for it is simple:

::

    |-- tests -> Tests that are shared by more than one virt backend
    |   `-- cfg -> Holds config snippets for the tests

Shared resources dir
--------------------

The virt tests often need a number of resources, be it a:

 - Disk image
 - Operating System CD
 - Scripts and executables to run in the guest
 - OEM installer files (kickstarts, windows answer files, among others)

We concentrate all those resources in the shared dir. If you look at its
structure, you'll see:

::

    |-- shared
    |   |-- autoit -> Windows specific automation files
    |   |-- blkdebug -> QEMU blkdebug config files
    |   |-- cfg -> Holds base config files
    |   |   `-- guest-os -> Holds a number of guest OS config snippets that'll create guest-os.cfg
    |   |       |-- Linux
    |   |       |   |-- Fedora
    |   |       |   |-- JeOS
    |   |       |   |-- LinuxCustom
    |   |       |   |-- OpenSUSE
    |   |       |   |-- RHEL
    |   |       |   |-- SLES
    |   |       |   `-- Ubuntu
    |   |       `-- Windows
    |   |           |-- Win2000
    |   |           |-- Win2003
    |   |           |-- Win2008
    |   |           |-- Win7
    |   |           |-- WindowsCustom
    |   |           |-- WinVista
    |   |           `-- WinXP
    |   |-- control -> Holds autotest control files to run in the guest
    |   |-- deps -> C programs that need to be compiled in the guest
    |   |   |-- test_clock_getres
    |   |   `-- test_cpu_flags
    |   |-- download.d -> Holds resource files, that can be used to download disks
    |   |-- scripts -> Holds python scripts to be executed in the guest
    |   |-- steps -> Recordings of guest interaction that can be replayed
    |   `-- unattended -> OEM install files (kickstarts, windows answer files)

Tools dir
---------

The tools dir contains a bunch of useful tools for test writers and virt-test
maintainers. Specially useful are the tools to run the unittests available
for virt-test, and run_pylint.py, which runs pylint in any python file you
might want, which helps to capture silly mistakes before they go public.

::

    tools/
    |-- cd_hash.py -> Calculates MD5 and SHA1 for ISOS (in fact, for any file)
    |-- check_patch.py -> Verify whether a github or patchwork patch is OK
    |-- common.py
    |-- common.pyc
    |-- download_manager.py -> Download resources, such as ISOS and guest images
    |-- koji_pkgspec.py -> Get info about packages in Koji or Brew
    |-- parallel.py
    |-- parallel.pyc
    |-- perf.conf
    |-- regression.py -> Compare virt test jobs performance data
    |-- reindent.py -> Fix indentation mistakes on your python files
    |-- run_pylint.py -> Static source checker for python
    |-- run_unittests.py -> Run all available virttest unittests
    |-- tapfd_helper.py -> Paste a qemu cmd line produced by autotest and run it
    `-- virt_disk.py -> Create floppy images and iso files

Virttest dir
------------

In this dir, goes most of the library code of virt test. Over the years, the
number of libraries grew quite a bit. Inside test code, those libraries are
usually imported like:

::

    from virttest import [library name]

Here's a listing with high level descriptions of each file:

::

    virttest
    |-- aexpect.py -> Controls subprocesses interactively
    |-- base_installer.py -> Base code for virt software install
    |-- bootstrap.py -> Functions to prepare environment previous to test exec
    |-- build_helper.py -> Code with rules to build software
    |-- cartesian_config.py -> The parser of the cartesian file format
    |-- common.py
    |-- data_dir.py -> Finds/sets the main data file
    |-- ElementPath.py -> Library to manipulate XML
    |-- ElementTree.py -> Library to manipulate XML
    |-- env_process.py -> Handles setup/cleanup pre/post tests
    |-- guest_agent.py -> Controls the qemu guest agent
    |-- http_server.py -> Simple server for kickstart installs
    |-- __init__.py
    |-- installer.py -> Code for virt software install
    |-- installer_unittest.py
    |-- iscsi.py -> Code to handle vm images in iscsi disks
    |-- iscsi_uinttest.py
    |-- libvirt_storage.py -> Create images for libvirt tests
    |-- libvirt_vm.py -> VM class for libvirt backend
    |-- libvirt_xml.py -> High level XML manipulation for libvirt test purposes
    |-- libvirt_xml_unittest.py
    |-- openvswitch.py -> Functions to deal with openvswitch network technology
    |-- ovirt.py -> Library to handle an ovirt server
    |-- ovs_utils.py -> Utils for the openvswitch test
    |-- passfd.c -> Python c library for filedescriptor passing
    |-- passfd.py -> Library for filedescriptor passing (python interface)
    |-- passfd_setup.py -> Compiles the passfd library
    |-- postprocess_iozone.py -> Code to analyze iozone results
    |-- ppm_utils.py -> Code to handle QEMU screenshot file format
    |-- propcan.py -> Class to handle sets of config values
    |-- propcan_unittest.py
    |-- qemu_installer.py -> Class to install qemu (git, rpm, etc)
    |-- qemu_io.py -> Code to call qemu-io, for testing
    |-- qemu_monitor.py -> Handles the qemu monitor interfaces (HMP and QMP)
    |-- qemu_qtree.py -> Creates a data structure representation of qemu qtree output
    |-- qemu_qtree_unittest.py
    |-- qemu_storage.py -> Handles image creation for the qemu test
    |-- qemu_virtio_port.py -> Code for dealing with qemu virtio ports
    |-- qemu_vm.py -> VM class for the qemu test
    |-- remote.py -> Functions to handle logins and remote transfers
    |-- rss_client.py -> Client for the windows shell tool developed for virt-tests
    |-- scheduler.py -> Functions for parallel testing
    |-- standalone_test.py -> Implements a small test harness for execution independent of autotest
    |-- step_editor.py -> Code for recording interaction with guests and replay them
    |-- storage.py -> Base code for disk image creation
    |-- syslog_server.py -> Simple syslog server to capture messages from OS installs
    |-- test_setup.py -> Tests prep code (Hugepages setup, among others)
    |-- utils_cgroup.py -> Utils to create and manipulate cgroups
    |-- utils_disk.py -> Utils to create ISOS and floppy images
    |-- utils_env.py -> Contains the class that holds the VM instances and other persistent info
    |-- utils_env_unittest.py
    |-- utils_koji.py -> Utils to interact with the Koji and Brew Buildsystems
    |-- utils_misc.py -> Utils that don't fit in broader categories
    |-- utils_misc_unittest.py
    |-- utils_net.py -> VM and Host network utils
    |-- utils_net_unittest.py
    |-- utils_params.py -> Contains the class that holds test config data
    |-- utils_spice.py -> Contains utils for spice testing
    |-- utils_test.py -> Contains high level common utilities for testing
    |-- utils_v2v.py -> Contains utilities for v2v testing
    |-- versionable_class.py -> Classes with multiple ancestors, for openvswitch testing
    |-- versionable_class_unittest.py
    |-- video_maker.py -> Creates a ogg/webm video from vm screenshots
    |-- virsh.py -> Calls and tests the virsh utility
    |-- virsh_unittest.py
    |-- virt_vm.py -> Base VM class, from where the specific tests derive from
    |-- xml_utils.py -> Utils for XML manipulation
    |-- xml_utils_unittest.py
    `-- yumrepo.py -> Lib to create yum repositories, test helper

As you can see, there's quite a lot of code. We try to keep it as organized as
possible, but if you have any problems just let us know (see ContactInfo).