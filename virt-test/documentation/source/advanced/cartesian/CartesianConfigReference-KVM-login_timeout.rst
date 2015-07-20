
login\_timeout
==============

Description
-----------

Sets the amount of time, in seconds, to wait for a session
(SSH/Telnet/Netcat) with the VM.

To set the timeout to 6 minutes:

::

    login_timeout = 360

Defined On
----------

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_
-  `client/tests/kvm/subtests.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/subtests.cfg.sample>`_

Used By
-------

-  `client/virt/tests/autotest.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/autotest.py>`_
-  `client/virt/tests/boot.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/boot.py>`_
-  `client/virt/tests/clock\_getres.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/clock_getres.py>`_
-  `client/virt/tests/ethtool.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/ethtool.py>`_
-  `client/virt/tests/file\_transfer.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/file_transfer.py>`_
-  `client/virt/tests/fillup\_disk.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/fillup_disk.py>`_
-  `client/virt/tests/guest\_s4.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/guest_s4.py>`_
-  `client/virt/tests/guest\_test.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/guest_test.py>`_
-  `client/virt/tests/iofuzz.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/iofuzz.py>`_
-  `client/virt/tests/ioquit.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/ioquit.py>`_
-  `client/virt/tests/iozone\_windows.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/iozone_windows.py>`_
-  `client/virt/tests/jumbo.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/jumbo.py>`_
-  `client/virt/tests/kdump.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/kdump.py>`_
-  `client/virt/tests/linux\_s3.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/linux_s3.py>`_
-  `client/virt/tests/lvm.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/lvm.py>`_
-  `client/virt/tests/mac\_change.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/mac_change.py>`_
-  `client/virt/tests/multicast.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/multicast.py>`_
-  `client/virt/tests/netperf.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/netperf.py>`_
-  `client/virt/tests/nicdriver\_unload.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/nicdriver_unload.py>`_
-  `client/virt/tests/nic\_promisc.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/nic_promisc.py>`_
-  `client/virt/tests/ping.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/ping.py>`_
-  `client/virt/tests/shutdown.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/shutdown.py>`_
-  `client/virt/tests/softlockup.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/softlockup.py>`_
-  `client/virt/tests/stress\_boot.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/stress_boot.py>`_
-  `client/virt/tests/vlan.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/vlan.py>`_
-  `client/virt/tests/watchdog.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/watchdog.py>`_
-  `client/virt/tests/whql\_client\_install.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/whql_client_install.py>`_
-  `client/virt/tests/whql\_submission.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/whql_submission.py>`_
-  `client/virt/tests/yum\_update.py <https://github.com/autotest/autotest/blob/master/client/virt/tests/yum_update.py>`_
-  `client/tests/kvm/tests/balloon\_check.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/balloon_check.py>`_
-  `client/tests/kvm/tests/cdrom.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/cdrom.py>`_
-  `client/tests/kvm/tests/cpu\_hotplug.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/cpu_hotplug.py>`_
-  `client/tests/kvm/tests/enospc.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/enospc.py>`_
-  `client/tests/kvm/tests/floppy.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/floppy.py>`_
-  `client/tests/kvm/tests/hdparm.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/hdparm.py>`_
-  `client/tests/kvm/tests/migration\_multi\_host.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/migration_multi_host.py>`_
-  `client/tests/kvm/tests/migration.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/migration.py>`_
-  `client/tests/kvm/tests/migration\_with\_file\_transfer.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/migration_with_file_transfer.py>`_
-  `client/tests/kvm/tests/migration\_with\_reboot.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/migration_with_reboot.py>`_
-  `client/tests/kvm/tests/multi\_disk.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/multi_disk.py>`_
-  `client/tests/kvm/tests/nic\_bonding.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/nic_bonding.py>`_
-  `client/tests/kvm/tests/nic\_hotplug.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/nic_hotplug.py>`_
-  `client/tests/kvm/tests/nmi\_watchdog.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/nmi_watchdog.py>`_
-  `client/tests/kvm/tests/pci\_hotplug.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/pci_hotplug.py>`_
-  `client/tests/kvm/tests/physical\_resources\_check.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/physical_resources_check.py>`_
-  `client/tests/kvm/tests/qemu\_img.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/qemu_img.py>`_
-  `client/tests/kvm/tests/set\_link.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/set_link.py>`_
-  `client/tests/kvm/tests/smbios\_table.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/smbios_table.py>`_
-  `client/tests/kvm/tests/stop\_continue.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/stop_continue.py>`_
-  `client/tests/kvm/tests/system\_reset\_bootable.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/system_reset_bootable.py>`_
-  `client/tests/kvm/tests/timedrift.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/timedrift.py>`_
-  `client/tests/kvm/tests/timedrift\_with\_migration.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/timedrift_with_migration.py>`_
-  `client/tests/kvm/tests/timedrift\_with\_reboot.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/timedrift_with_reboot.py>`_
-  `client/tests/kvm/tests/timedrift\_with\_stop.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/timedrift_with_stop.py>`_
-  `client/tests/kvm/tests/trans\_hugepage\_defrag.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/trans_hugepage_defrag.py>`_
-  `client/tests/kvm/tests/trans\_hugepage.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/trans_hugepage.py>`_
-  `client/tests/kvm/tests/trans\_hugepage\_swapping.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/trans_hugepage_swapping.py>`_
-  `client/tests/kvm/tests/usb.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/usb.py>`_
-  `client/tests/kvm/tests/vmstop.py <https://github.com/autotest/autotest/blob/master/client/tests/kvm/tests/vmstop.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

