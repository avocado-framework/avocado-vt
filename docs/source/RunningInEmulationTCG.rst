.. _emulation:

===============================
Running in emulation mode (TCG)
===============================

Sometimes it's useful to run Avocado-vt in emulation mode (eg. when
checking PR about different architecture, or to debug certain feature
while executing the test). As this is not default, extra arguments are
usually required.

Shared for all architectures is that you need the image. We supply
JeOS for most of the architectures, so you should be able to get
it via::

    $ avocado vt-bootstrap --vt-guest-os JeOS.$VERSION.$ARCH

where:

* ``VERSION`` is JeOS version (when writing this document it was ``27``)
* ``ARCH`` is the desired architecture (eg. aarch64)

Or you can run any of the ``unattended_install`` tests with
``--vt-guest-os`` of your choice (very slow).

When running the tests, on top of the usual arguments, you usually
need to specify:

* ``--vt-qemu-bin`` - path to binary that supports expected architecture
  (eg. ``/usr/local/bin/qemu-system-aarch64``)
* ``--vt-qemu-dst-bin`` - for migration tests you need also to specify
  the destination qemu binary (otherwise default one is used)
* ``enable_kvm=no`` - to disable KVM (if necessary)

.. note::

   Some test require additional dependencies and are marked as ``no JeOS``
   (another group is marked as ``only RHEL``) but it might be useful for
   debugging purposes to use them with JeOS. You can do that by symlinking
   the ``$avocado-vt-data/images/jeos-$version-$arch.qcow2`` to
   ``$avocado-vt-data/images/rhel${version}devel-$arch.qcow2`` and using
   the boot test with ``--vt-guest-os RHEL.$version``. To add extra
   packages use ``ctrl+Z`` when it's about to ssh in. Then you can
   ssh to that guest from your machine, run ``dnf install ...``
   to install the extra packages (``gcc`` suffices for most test), shut
   the machine down, backup it to ``$name.backup`` and resume the ``boot``
   test by ``ctrl+Z``. Obviously the test will fail, refreshes the image
   from ``$name.backup`` but since then you have slightly fattier JeOS
   symlinked to RHEL capable of running some extended tests without
   the need to run full installation in TCG mode. Beware, vt-bootstrap
   might overwrite the `.backup` from archive.

aarch64
=======

ARM always requires `cpu_model` as well as `machine_type`. To
get list of available models you can run ``qemu-system-aarch64
-cpu help -M virt`` (note: not all listed cpus are bootable).
By default Avocado-vt uses ``-machine $machine_type,gic-version=host``
to use host's GIC version, but this is not possible to evaluate
in TCG (especially without GIC on x86) so one needs to either
pick a fixed version or simply use qemu default by cleaning
the ``machine_type_extra_params``. Complete example would be::

   $ avocado vt-bootstrap --vt-guest-os JeOS.27.aarch64
   $ avocado --show all run --vt-extra-params enable_kvm=no cpu_model=cortex-a57 \
       machine_type_extra_params='' --vt-machine-type aarch64 --vt-arch arm64-pci \
       --vt-qemu-bin /usr/local/bin/qemu-system-aarch64 -- boot


ppc64/ppc64le
=============

PowerPC can use either BE or LE instructions, but from qemu point of view
nothing changes. Still for Avocado-vt you either have to specify
``--vt-arch ppc64`` or ``--vt-arch ppc64le`` to choose the right distribution
image (both were available as JeOS when writing this document). Apart from
this no additional tweaks are necessary::

   $ avocado vt-bootstrap --vt-guest-os JeOS.27.ppc64
   $ avocado --show all run --vt-extra-params enable_kvm=no --vt-arch ppc64 \
       --vt-machine-type pseries --vt-qemu-bin /usr/local/bin/qemu-system-ppc64 -- boot

   $ avocado vt-bootstrap --vt-guest-os JeOS.27.ppc64le
   $ avocado --show all run --vt-extra-params enable_kvm=no --vt-arch ppc64le \
       --vt-machine-type pseries --vt-qemu-bin /usr/local/bin/qemu-system-ppc64 -- boot


s390x
=====

For KVM execution Avocado-vt uses ``-cpu host`` on s390x, which is not
possible without KVM. To execute in TCG mode you need to replace it with
either a supported CPU type or simply leave it blank::

   $ avocado vt-bootstrap --vt-guest-os JeOS.27.s390x
   $ avocado --show all run --vt-extra-params enable_kvm=no cpu_model='' --vt-arch s390x \
       --vt-machine-type s390-virtio --vt-qemu-bin /usr/local/bin/qemu-system-s390x -- boot

riscv64
=======

When writing this document, riscv64 was not available as JeOS and even
Fedora support was not straight forward. See `riscv64_setup`_ for setup
instructions. Apart from the setup running riscv64 does not require any
additional arguments::

   $ avocado run --vt-machine-type riscv64-mmio --vt-arch riscv64 \
       --vt-extra-params enable_kvm=no --vt-guest-os Fedora.28 -- boot
