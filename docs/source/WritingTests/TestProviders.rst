==============
Test Providers
==============

Test providers are the conjunction of a loadable module mechanism
inside Avocado-VT that can pull a directory that will provide tests, config
files and any dependencies, and those directories. The design goals behind
test providers are:

* Make it possible for other organizations to maintain test repositories, in other arbitrary git repositories.

* Stabilize API and enforce separation of core Avocado-VT functionality and tests.

The test provider spec is divided in Provider Layout and Definition files.

Test Provider Layout
====================

::

    .
    |-- backend_1        -> Backend name. The actual name doesn't matter.
    |   |-- cfg          -> Test config directory. Holds base files for the test runner.
    |   |-- deps         -> Auxiliary files such as ELF files, Windows executables, images that tests need.
    |   |-- provider_lib -> Shared libraries among tests.
    |   `-- tests        -> Python test files.
    |       `-- cfg      -> Config files for tests.
    `-- backend_2
        |-- cfg
        |-- deps
        |-- provider_lib
        `-- tests
            `-- cfg


In fact, Avocado-VT libraries are smart enough to support arbitrary organization
of python and config files inside the 'tests' directory. You don't need to name
the top level sub directories after backend names, although that certainly makes
things easier. The term 'backend' is used to refer to the supported virtualization
technologies by Avocado-VT. As of this writing, the backends known by Avocado-VT
are:

* generic (tests that run in multiple backends)
* qemu
* openvswitch
* libvirt
* v2v
* libguestfs
* lvsb

The reason why you don't need to name the directories after the backend names
is that you can configure a test definition file to point out any dir name. We'll
get into

Types of Test Providers
=======================

Each test provider can be either a local filesystem directory, or a subdirectory
of a git repository. Of course, the git repo subdirectory can be the repo root
directory, but one of the points of the proposal is that people can hold
Avocado-VT providers inside git repos of other projects. Say qemu wants to
maintain its own provider, they can do this by holding the tests, say, inside
a tests/avocado_vt subdirectory inside qemu.git.

Test Provider definition file
=============================

The main Avocado-VT suite needs a way to know about test providers. It does that
by scanning definition files inside the 'test-providers.d' sub directory.
Definition files are `config parser files <http://docs.python.org/2/library/configparser.html>`
that encode information from a test provider. Here's an example structure of a
test provider file:

::

    [provider]

    # Test provider URI (default is a git repository, fallback to standard dir)
    uri: git://git-provider.com/repo.git
    #uri: /path-to-my-git-dir/repo.git
    #uri: http://bla.com/repo.git
    #uri: file:///usr/share/tests

    # Optional git branch (for git repo type)
    branch: master

    # Optionall git commit reference (tag or sha1)
    ref: e44231e88300131621586d24c07baa8e627de989

    # Pubkey: File containing public key for signed tags (git)
    pubkey: example.pub

    # What follows is a sequence of sections for any backends that this test
    # provider implements tests for. You must specify the sub directories of
    # each backend dir, reason why the subdir names can be arbitrary.

    [qemu]
    # Optional subdir (place inside repo where the actual tests are)
    # This is useful for projects to keep virt tests inside their
    # (larger) test repos. Defaults to ''.
    subdir: src/tests/qemu/

    [agnostic]
    # For each test backend, you may have different sub directories
    subdir: src/tests/generic/

Example of a default Avocado-VT provider file:

::

    [provider]
    uri: https://github.com/autotest/tp-qemu.git
    [generic]
    subdir: generic/
    [qemu]
    subdir: qemu/
    [openvswitch]
    subdir: openvswitch/

Let's say you want to use a directory in your file system
(/usr/share/tests/virt-test):

::

    [provider]
    uri: file:///usr/share/tests/
    [generic]
    subdir: virt-test/generic/
    [qemu]
    subdir: virt-test/qemu/
    [openvswitch]
    subdir: virt-test/openvswitch/

