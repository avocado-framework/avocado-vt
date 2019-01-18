.. _experimental:

=====================
Experimental features
=====================

.. _riscv64_setup:

riscv64
=======

The support for riscv64 is very experimental and requires special
preparations. Basically you need to prepare your system according to:

    https://fedorapeople.org/groups/risc-v/disk-images/readme.txt

Which means you need to install latest qemu-system-riscv (tested
with qemu ``00928a421d47f49691cace1207481b7aad31b1f1``) or install
the one provided by Rich:

    https://copr.fedorainfracloud.org/coprs/rjones/riscv/

And you need to download a suitable image and bootable kernel to
the right location:

* kernel: https://fedorapeople.org/groups/risc-v/disk-images/bbl
  needs to be downloaded in ``$AVOCADO_VT_DATA/images/f28-riscv64-kernel``
* image: https://fedorapeople.org/groups/risc-v/disk-images/stage4-disk.img.xz
  needs to be downloaded in ``$AVOCADO_VT_DATA/images/``, extracted
  and converted to ``qcow2`` using name ``f28-riscv64.qcow2``.

Basically you can go into ``$AVOCADO_VT_DATA/images`` and execute::

    curl https://fedorapeople.org/groups/risc-v/disk-images/bbl -o f28-riscv64-kernel
    curl https://fedorapeople.org/groups/risc-v/disk-images/stage4-disk.img.xz | xz -d > stage4-disk.img
    qemu-img convert -f raw -O qcow2 stage4-disk.img f28-riscv64.qcow2
    rm stage4-disk.img

Also I'd recommend booting the guest::

    qemu-system-riscv64 \
        -nographic \
        -machine virt \
        -smp 4 \
        -m 2G \
        -kernel f28-riscv64-kernel \
        -object rng-random,filename=/dev/urandom,id=rng0 \
        -device virtio-rng-device,rng=rng0 \
        -append "console=ttyS0 ro root=/dev/vda" \
        -device virtio-blk-device,drive=hd0 \
        -drive file=f28-riscv64.qcow2,format=qcow2,id=hd0 \
        -device virtio-net-device,netdev=usernet \
        -netdev user,id=usernet,hostfwd=tcp::10000-:22

and running the Fedora-25.ks post-install steps::

    dnf -y install @standard @c-development @development-tools python net-tools sg3_utils python-pip
    grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
    dhclient
    chkconfig sshd on
    iptables -F
    systemctl mask tmp.mount
    echo 0 > /selinux/enforce
    sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-eth0
    # if package groups were missing from main installation repo
    # try again from installed system
    dnf -y groupinstall c-development development-tools
    # include avocado: allows using this machine with remote runner
    # Fallback to pip as it's not yet built for riscv64
    dnf -y install python2-avocado || pip install python2-avocado

.. tip:: If you want to use riscv without kvm (eg. on x86 host) use something
         like ``avocado run --vt-machine-type riscv64-mmio --vt-arch riscv64
         --vt-extra-params enable_kvm=no --vt-guest-os Fedora.28 -- boot``
         which sets the right machine/arch and disables kvm (uses tcg).
