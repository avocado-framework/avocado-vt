=================
GlusterFS support
=================

GlusterFS is an open source, distributed file system capable of scaling to several petabytes (actually, 72 brontobytes!) and handling thousands of clients. GlusterFS clusters together storage building blocks over Infiniband RDMA or TCP/IP interconnect, aggregating disk and memory resources and managing data in a single global namespace. GlusterFS is based on a stackable user space design and can deliver exceptional performance for diverse workloads.

More details of GlusterFS can be found under

https://www.gluster.org/

GlusterFS is added as a new block backend for qemu and to make use of this feature we require the following components.

More details of GlusterFS-QEMU Integration can be found under

http://raobharata.wordpress.com/2012/10/29/qemu-glusterfs-native-integration/

1. Qemu- 1.3, 03Dec2012
2. GlusterFS-3.4
3. Libvirt-1.0.1, 15Dec2012

How to use in Avocado-VT
------------------------

You can use Avocado-VT to test GlusterFS support with following steps.

1) Edit qemu/cfg/tests.cfg with following changes,

::

    only glusterfs_support
    remove ‘only no_glusterfs_support’ line from the file

2) Optionally, edit shared/cfg/guest-hw.cfg for the gluster volume name and brick path,
default is going to be,

::

    gluster_volume_name = test-vol
    gluster_brick = /tmp/gluster

How to use manually
-------------------

The following is just an example to show how we create gluster volume and run a guest on that volume manually.

Starting Gluster daemon
-----------------------

::

    $ service glusterd start


Gluster volume creation
-----------------------

::

    $ gluster volume create [volume-name]  [hostname/host_ip]:/[brick_path]

E.g.: `gluster volume create test-vol satheesh.ibm.com://home/satheesh/images_gluster`


Qemu Img creation
-----------------

::

    $ qemu-img create gluster://[hostname]:0/[volume-name]/[image-name] [size]

E.g.: `qemu-img create gluster://satheesh.ibm.com:0/test-vol/test_gluster.img 10G`


Example of qemu cmd Line
------------------------

::

    $ qemu-system-x86_64 --enable-kvm -smp 4 -m 2048 -drive file=gluster://satheesh.ibm.com/test-vol/test_gluster.img,if=virtio -net nic,macaddr=52:54:00:09:0a:0b -net tap,script=/path/to/qemu-ifupVirsh
