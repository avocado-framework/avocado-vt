==========
Networking
==========

Here we have notes about networking setup in virt-test.

Configuration
-------------

How to configure to allow all the traffic to be forwarded across the virbr0 bridge:
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

   echo "-I FORWARD -m physdev --physdev-is-bridged -j ACCEPT" > /etc/sysconfig/iptables-forward-bridged
   lokkit --custom-rules=ipv4:filter:/etc/sysconfig/iptables-forward-bridged
   service libvirtd reload


How to configure Static IP address in virt-test
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sometimes, we need to test with guest(s) which have static ip address(es).

- eg. No real/emulated DHCP server in test environment.
- eg. Test with old image we don't want to change the net config.
- eg. Test when DHCP exists problem.

Create a bridge (for example, 'vbr') in host, configure its ip to 192.168.100.1, guest
can access host by it. And assign nic(s)' ip in tests.cfg, and execute test as usual.

tests.cfg:

::

     ip_nic1 = 192.168.100.119
     nic_mac_nic1 = 11:22:33:44:55:67
     bridge = vbr

TestCases
---------

Ntttcp
~~~~~~

The Nttcp test suite is a network performance test for windows, developed by
Microsoft. It is *not* a freely redistributable binary, so you must download
it from the website, here's the direct link for download (keep in mind it might
change):

http://download.microsoft.com/download/f/1/e/f1e1ac7f-e632-48ea-83ac-56b016318735/NT%20Testing%20TCP%20Tool.msi

The knowledge base article associated with it is:

http://msdn.microsoft.com/en-us/windows/hardware/gg463264

You need to add the package to winutils.iso, the iso with utilities used to
test windows. First, download the iso. :doc:`The get started documentation <../basic/GetStarted>`
can help you out with downloading if you like it, but the direct download
link is here:

http://lmr.fedorapeople.org/winutils/winutils.iso

You need to put all its contents on a folder and create a new iso. Let's say you
want to download the iso to ``/home/kermit/Downloads/winutils.iso``.
You can create the directory, go to it:

::

    mkdir -p /home/kermit/Downloads
    cd /home/kermit/Downloads

Download the iso, create 2 directories, 1 for the mount, another for the
contents:

::

    wget http://people.redhat.com/mrodrigu/kvm/winutils.iso
    mkdir original
    sudo mount -o loop winutils.iso original
    mkdir winutils

Copy all contents from the original cd to the new structure:

::

    cp -r original/* winutils/

Create the destination nttcp directory on that new structure:

::

    mkdir -p winutils/NTttcp

Download the installer and copy autoit script to the new structure, unmount the orginal mount:

::

    cd winutils/NTttcp
    wget http://download.microsoft.com/download/f/1/e/f1e1ac7f-e632-48ea-83ac-56b016318735/NT%20Testing%20TCP%20Tool.msi -O "winutils/NTttcp/NT Testing TCP Tool.msi"
    cp /usr/local/autotest/client/virt/scripts/ntttcp.au3 ./
    sudo umount original

Backup the old winutils.iso and create a new winutils.iso using mkisofs:

::

    sudo mv winutils.iso winutils.iso.bak
    mkisofs -o winutils.iso -max-iso9660-filenames -relaxed-filenames -D --input-charset iso8859-1 winutils

And that is it. Don't forget to keep winutils in an appropriate location that
can be seen by virt-test.
