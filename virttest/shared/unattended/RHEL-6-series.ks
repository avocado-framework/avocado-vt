install
KVM_TEST_MEDIUM
text
lang en_US.UTF-8
keyboard us
key --skip
network --bootproto dhcp
rootpw 123456
firewall --enabled --ssh
selinux --enforcing
timezone --utc America/New_York
firstboot --disable
bootloader --location=mbr --append="console=tty0 console=ttyS0,115200"
zerombr
xconfig --startxonboot
#partitioning
clearpart --all --initlabel
part /boot --fstype=ext4 --size=500
part pv.01  --grow --size=1
volgroup VolGroup --pesize=131072  pv.01
logvol swap --name=LogVol_swap --vgname=VolGroup --size=4096
logvol / --fstype=ext4 --name=LogVol_root --vgname=VolGroup --size=1 --grow
poweroff
KVM_TEST_LOGGING

%packages --ignoremissing
@base
@core
@development
@additional-devel
@debugging-tools
@network-tools
@basic-desktop
@desktop-platform
@fonts
@general-desktop
@graphical-admin-tools
@x11
lftp
gcc
gcc-c++
patch
make
git
nc
net-tools
NetworkManager
ntpdate
redhat-lsb
watchdog
coreutils
libblkid-devel
koji
usbutils
qemu-guest-agent
sg3_utils
xfsprogs
lsscsi
libaio-devel
perl-Time-HiRes
glibc-devel
glibc-static
scsi-target-utils

%post
function ECHO { for TTY in ttyS0 hvc0; do echo "$*" > /dev/$TTY; done }
ECHO "OS install is completed"
grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
dhclient
chkconfig sshd on
iptables -F
echo 0 > /selinux/enforce
chkconfig NetworkManager on
sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-*
ECHO "Remove 70-persistent-net.rules (prevent network device rename)"
rm -f /etc/udev/rules.d/70-persistent-net.rules
ECHO 'Post set up finished'
%end
