install
KVM_TEST_MEDIUM
graphical
poweroff
lang en_US.UTF-8
keyboard us
key --skip
network --bootproto dhcp
rootpw 123456
firewall --enabled --ssh
selinux --enforcing
timezone --utc Asia/Shanghai
firstboot --disable
bootloader --location=mbr --append="console=tty0 console=hvc0,38400"
zerombr
#partitioning
clearpart --all --initlabel
autopart
xconfig --startxonboot

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
NetworkManager
ntpdate
redhat-lsb
qemu-guest-agent
sg3_utils
libaio-devel
lsscsi
perl-Time-HiRes
flex
scsi-target-utils
-strace32

%post
ln -sf /dev/null /etc/udev/rules.d/70-persistent-net.rules
echo "OS install is completed" > /dev/hvc0
echo "remove rhgb quiet by grubby" > /dev/hvc0
grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
echo "dhclient" > /dev/hvc0
dhclient
echo "get repo" > /dev/ttyS0
rpm -ivh https://dl.fedoraproject.org/pub/epel/epel-release-latest-6.noarch.rpm
echo "yum makecache" > /dev/hvc0
yum makecache
echo "yum install -y stress" > /dev/hvc0
yum install -y stress
echo "chkconfig sshd on" > /dev/hvc0
chkconfig sshd on
echo "iptables -F" > /dev/hvc0
iptables -F
echo "echo 0 > selinux/enforce" > /dev/hvc0
echo 0 > /selinux/enforce
echo "chkconfig NetworkManager on" > /dev/hvc0
chkconfig NetworkManager on
echo "update ifcfg-*" > /dev/hvc0
sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-*
sed -i "/UUID/d" /etc/sysconfig/network-scripts/ifcfg-*
echo "ifconfig -a | tee /dev/hvc0" >> /etc/rc.local
echo 'Post set up finished' > /dev/hvc0
%end
