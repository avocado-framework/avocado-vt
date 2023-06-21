Setting up a Regression Test Farm for KVM
=========================================

You have all upstream code, and you're wondering if the internal Red Hat
testing of KVM has a lot of internal 'secret sauce'. No, it does not.

However, it is a complex endeavor, since there are *lots* of details involved.
The farm setup and maintenance is not easy, given the large amounts of things
that can fail (machines misbehave, network problems, git repos unavailable,
so on and so forth). *You have been warned*.

With all that said, we'll share what we have been doing. We did clean up our
config files and extensions and released them upstream, together with this
procedure, that we hope it will be useful to you guys. Also, this will cover
KVM testing on a single host, as tests involving multiple hosts and Libvirt
testing are a work in progress.

The basic steps are:

1) Install an autotest server.
2) Add machines to the server (test nodes). Those machines are the virt hosts
   that will be tested.
3) Prepare the virt test jobs and schedule them.
4) Set up cobbler in your environment so you can install hosts.
5) Lots of trial and error until you get all little details sorted out.

We took years repeating all the steps above and perfecting the process, and we
are willing to document it all to the best extent possible. I'm afraid however,
that you'll have to do your homework and adapt the procedure to your environment.

Some conventions
----------------

We are assuming you will install autotest to its default upstream location

/usr/local/autotest

Therefore a lot of paths referred here will have this as the base dir.

CLI vs Web UI
--------------

During this text, we'll use frequently the terms CLI and Web UI.

By CLI we mean specifically the program:

/usr/local/autotest/cli/autotest-rpc-client

That is located in the autotest code checkout.

By Web UI, we mean the web interface of autotest, that can be accessed through

http://your-autotest-server.com/afe


Step 1 - Install an autotest server
-----------------------------------

Provided that you have internet on your test lab, this should be the easiest
step. Pick up either a VM accessible in your lab, or a bare metal machine
(it really doesn't make a difference, we use a VM here). We'll refer
it from now on as the "Server" box.


The hard drive of the Server should hold enough room for test results. We found
out that at least 250 GB holds data for more than 6 months, provided that
QEMU doesn't crash a lot.

You'll follow the procedure described on

https://github.com/autotest/autotest/wiki/AutotestServerInstallRedHat

for Red Hat derivatives (such as Fedora and RHEL), and

https://github.com/autotest/autotest/wiki/AutotestServerInstall

for Debian derivatives (Debian, Ubuntu).

Note that using the install script referred right in the beginning of the
documentation is the preferred method, and should work pretty well if you have
internet on your lab. In case you don't have internet there, you'd need to
follow the instructions after the 'installing with the script' instructions.
Let us know if you have any problems.

Step 2 - Add test machines
--------------------------

It should go without saying, but the machines you have to add have to be
virtualization capable (support KVM).

You can add machines either by using the CLI or the Web UI, following
the documentation:

https://github.com/autotest/autotest/wiki/ConfiguringHosts

If you don't want to read that, I'll try to write a quick howto.

Say you have two x86_64 hosts, one AMD and the other, Intel. Their hostnames are:

foo-amd.bazcorp.com
foo-intel.bazcorp.com

I would create 2 labels, amd64 and intel64, I would also create a label to
indicate the machines can be provisioned by cobbler. This is because you
can tell autotest to run a job in any machine that matches a given label.

Logged as the autotest user:

::

    $ /usr/local/autotest/cli/autotest-rpc-client label create -t amd64
    Created label:
        'amd64'
    $ /usr/local/autotest/cli/autotest-rpc-client label create -t intel64
    Created label:
        'intel64'
    $ /usr/local/autotest/cli/autotest-rpc-client label create hostprovisioning
    Created label:
        'hostprovisioning'

Then I'd create each machine with the appropriate labels

::

    $ /usr/local/autotest/cli/autotest-rpc-client host create -t amd64 -b hostprovisioning foo-amd.bazcorp.com
    Added host:
        foo-amd.bazcorp.com

    $ /usr/local/autotest/cli/autotest-rpc-client host create -t intel64 -b hostprovisioning foo-intel.bazcorp.com
    Added host:
        foo-intel.bazcorp.com


Step 3 - Prepare the test jobs
------------------------------

Now you have to copy the plugin we have developed to extend the CLI to parse
additional information for the virt jobs:

::

    $ cp /usr/local/autotest/contrib/virt/site_job.py /usr/local/autotest/cli/

This should be enough to enable all the extra functionality.

You also need to copy the site-config.cfg file that we published as a reference,
to the qemu config module:

::

    $ cp /usr/local/autotest/contrib/virt/site-config.cfg /usr/local/autotest/client/tests/virt/qemu/cfg

Be aware that you *need* to read this file well, and later, configure it to your
testing needs. We specially stress that you might want to create private git
mirrors of the git repos you want to test, so you tax the upstream mirrors
less, and have increased reliability.

Right now it is able to run regression testing on Fedora 18, and upstream kvm,
provided that you have a cobbler instance functional, with a profile called
f18-autotest-kvm that can be properly installed on your machines. Having that
properly set up may open another can of worms.

One simple way to schedule the jobs, that we does use at our server, is to
use cron to schedule daily testing jobs of the things you want to test. Here
is an example that should work 'out of the box'. Provided that you have an
internal mailing list that you created with the purpose of receiving email
notifications, called autotest-virt-jobs@foocorp.com, you can stick that
on the crontab of the user autotest in the Server:

::

    07 00 * * 1-7 /usr/local/autotest/cli/autotest-rpc-client job create -B never -a never -s -e autotest-virt-jobs@foocorp.com -f "/usr/local/autotest/contrib/virt/control.template" -T --timestamp -m '1*hostprovisioning' -x 'only qemu-git..sanity' "Upstream qemu.git sanity"
    15 00 * * 1-7 /usr/local/autotest/cli/autotest-rpc-client job create -B never -a never -s -e autotest-virt-jobs@foocorp.com -f "/usr/local/autotest/contrib/virt/control.template" -T --timestamp -m '1*hostprovisioning' -x 'only f18..sanity' "Fedora 18 koji sanity"
    07 01 * * 1-7 /usr/local/autotest/cli/autotest-rpc-client job create -B never -a never -s -e autotest-virt-jobs@foocorp.com -f "/usr/local/autotest/contrib/virt/control.template" -T --timestamp -m '1*hostprovisioning' -x 'only qemu-git..stable' "Upstream qemu.git stable"
    15 01 * * 1-7 /usr/local/autotest/cli/autotest-rpc-client job create -B never -a never -s -e autotest-virt-jobs@foocorp.com -f "/usr/local/autotest/contrib/virt/control.template" -T --timestamp -m '1*hostprovisioning' -x 'only f18..stable' "Fedora 18 koji stable"

That should be enough to have one sanity and stable job for:

* Fedora 18.
* qemu.git userspace and kvm.git kernel.

What does these 'stable' and 'sanity' jobs do? In short:

* Host OS (Fedora 18) installation through cobbler
* Latest kernel for the Host OS installation (either the last kernel update build for fedora, or check out, compile and install kvm.git).

sanity job
----------

* Install latest Fedora 18 qemu-kvm, or compiles the latest qemu.git
* Installs a VM with Fedora 18, boots, reboots, does simple, single host migration with all supported protocols
* Takes about two hours. In fact, internally we test more guests, but they are not widely available (RHEL 6 and Windows 7), so we just replaced them with Fedora 18.

stable job
----------

* Same as above, but many more networking, timedrift and other tests

Setup cobbler to install hosts
------------------------------

Cobbler is an installation server, that control DHCP and/or PXE boot for your
x86_64 bare metal virtualization hosts. You can learn how to set it up in the
following resource:

https://github.com/cobbler/cobbler/wiki

You will set it up for simple installations, and you probably just need to
import a Fedora 18 DVD into it, so it can be used to install your hosts.
Following the import procedure, you'll have a 'profile' created, which is a
label that describes an OS that can be installed on your virtualization host.
The label we chose, as already mentioned is f18-autotest-kvm. If you want to
change that name, you'll have to change site-config.cfg accordingly.

Also, you will have to add your test machines to your cobbler server, and
will have to set up remote control (power on/off) for them.

The following is important:

*The hostname of your machine in the autotest server has to be the name of your system in cobbler*.

So, for the hypothetical example you'll have to have set up
systems with names foo-amd.bazcorp.com foo-intel.bazcorp.com in cobbler. That's
right, the 'name' of the system has to be the 'hostname'. Otherwise, autotest
will ask cobbler and cobbler will not know which machine autotest is taking about.

Other assumptions we have here:

1) We have a (read only, to avoid people deleting isos by mistake) NFS share
that has the Fedora 18 DVD and other ISOS. The structure for the base dir
could look something like:

::

    .
    |-- linux
    |   `-- Fedora-18-x86_64-DVD.iso
    `-- windows
        |-- en_windows_7_ultimate_x64_dvd_x15-65922.iso
        |-- virtio-win.iso
        `-- winutils.iso

This is just in case you are legally entitled to download and use Windows 7,
for example.

2) We have another NFS share with space for backups of qcow2 images that got
corrupted during testing, and you want people to analyze them. The structure
would be:

::

    .
    |-- foo-amd
    `-- bar-amd

That is, one directory for each host machine you have on your grid. Make sure they
end up being properly configured in the kickstart.

Now here is one excerpt of kickstart with some of the gotchas we learned
with experience. Some notes:

* This is not a fully formed, functional kickstart, just in case you didn't notice.
* This is provided in the hopes you read it, understand it and adapt things to your needs. If you paste this into your kickstart and tell me it doesn't work, I WILL silently ignore your email, and if you insist, your emails will be filtered out and go to the trash can.


::

    install

    text
    reboot
    lang en_US
    keyboard us
    rootpw --iscrypted [your-password]
    firewall --disabled
    selinux --disabled
    timezone --utc America/New_York
    firstboot --disable
    services --enabled network --disabled NetworkManager
    bootloader --location=mbr
    ignoredisk --only-use=sda
    zerombr
    clearpart --all --drives=sda --initlabel
    autopart
    network --bootproto=dhcp --device=eth0 --onboot=on

    %packages
    @core
    @development-libs
    @development-tools
    @virtualization
    wget
    dnsmasq
    genisoimage
    python-imaging
    qemu-kvm-tools
    gdb
    iasl
    libvirt
    ntpdate
    gstreamer-plugins-good
    gstreamer-python
    dmidecode
    popt-devel
    libblkid-devel
    pixman-devel
    mtools
    koji
    tcpdump
    bridge-utils
    dosfstools
    %end

    %post

    echo "[nfs-server-that-holds-iso-images]:[nfs-server-that-holds-iso-images]/base_path/iso /var/lib/virt_test/isos nfs ro,defaults 0 0" >> /etc/fstab
    echo "[nfs-server-that-holds-iso-images]:[nfs-server-that-holds-iso-images]/base_path/steps_data  /var/lib/virt_test/steps_data nfs rw,nosuid,nodev,noatime,intr,hard,tcp 0 0" >> /etc/fstab
    echo "[nfs-server-that-has-lots-of-space-for-backups]:/base_path/[dir-that-holds-this-hostname-backups] /var/lib/virt_test/images_archive nfs rw,nosuid,nodev,noatime,intr,hard,tcp 0 0" >> /etc/fstab
    mkdir -p /var/lib/virt_test/isos
    mkdir -p /var/lib/virt_test/steps_data
    mkdir -p /var/lib/virt_test/images
    mkdir -p /var/lib/virt_test/images_archive

    mkdir --mode=700 /root/.ssh
    echo 'ssh-dss [the-ssh-key-of-the-Server-autotest-user]' >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys

    ntpdate [your-ntp-server]
    hwclock --systohc

    systemctl mask tmp.mount
    %end

Painful trial and error process to adjust details
-------------------------------------------------

After all that, you can start running your test jobs and see what things will
need to be fixed. You can run your jobs easily by logging into your Server, with
the autotest user, and use the command:

::

    $ /usr/local/autotest/cli/autotest-rpc-client job create -B never -a never -s -e autotest-virt-jobs@foocorp.com -f "/usr/local/autotest/contrib/virt/control.template" -T --timestamp -m '1*hostprovisioning' -x 'only f18..sanity' "Fedora 18 koji sanity"

As you might have guessed, this will schedule a Fedora 18 sanity job. So go
through it and fix things step by step. If anything, you can take a look at
this:

https://github.com/autotest/autotest/wiki/DiagnosingFailures

And see if it helps. You can also ask on the mailing list, but *please*,
*pretty please* do your homework before you ask us to guide you through all
the process step by step. This is already a step by step procedure.

All right, good luck, and happy testing!
