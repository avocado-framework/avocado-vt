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
part /boot --fstype=ext3 --size=500
part pv.01  --grow --size=1
volgroup VolGroup --pesize=131072  pv.01
logvol swap --name=LogVol_swap --vgname=VolGroup --size=4096
logvol / --fstype=ext4 --name=LogVol_root --vgname=VolGroup --size=1 --grow
poweroff
KVM_TEST_LOGGING

%packages
@base
@development-libs
@development-tools
@gnome-desktop
@base-x
@core
xorg-x11-utils
xorg-x11-server-Xnest
kexec-tools
watchdog
gcc
patch
make
nc
ntp
redhat-lsb
sg3_utils
lsscsi
libaio-devel
NetworkManager

%post
function ECHO { for TTY in ttyS0 hvc0; do echo "$*" > /dev/$TTY; done }
ECHO "OS install is completed"
grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
grubby --args="divider=10 crashkernel=128M@16M" --update-kernel=$(grubby --default-kernel)
dhclient
chkconfig sshd on
chkconfig NetworkManager on
iptables -F
echo 0 > /selinux/enforce
sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-eth0
ECHO 'Post set up finished'
%end
