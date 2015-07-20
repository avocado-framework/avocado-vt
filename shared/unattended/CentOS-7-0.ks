install
KVM_TEST_MEDIUM
GRAPHICAL_OR_TEXT
poweroff
lang en_US.UTF-8
keyboard us
network --onboot yes --device eth0 --bootproto dhcp
rootpw 123456
firewall --enabled --ssh
selinux --enforcing
timezone --utc America/New_York
firstboot --disable
bootloader --location=mbr --append="console=tty0 console=ttyS0,115200"
zerombr
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
@fonts
@x11
@gnome-desktop
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
numactl-libs
numactl
sg3_utils
hdparm
lsscsi
libaio-devel
perl-Time-HiRes
flex
prelink
%end

%post
function ECHO { for TTY in `cat /proc/consoles | cut -f1 -d' '`; do echo "$*" > /dev/$TTY; done }
ECHO "OS install is completed"
ECHO "remove rhgb quiet by grubby"
grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
ECHO "dhclient"
dhclient
ECHO "get repo"
wget http://fileshare.englab.nay.redhat.com/pub/section2/repo/epel/rhel-autotest.repo -O /etc/yum.repos.d/rhel-autotest.repo
ECHO "yum makecache"
yum makecache
ECHO "yum install -y stress"
yum install -y stress
ECHO "chkconfig sshd on"
chkconfig sshd on
ECHO "PermitRootLogin in /etc/ssh/sshd_config"
sed -i 's/#PermitRootLogin yes/PermitRootLogin yes/g' /etc/ssh/sshd_config
ECHO "iptables -F"
iptables -F
ECHO "echo 0 > selinux/enforce"
echo 0 > /selinux/enforce
ECHO "chkconfig NetworkManager on"
chkconfig NetworkManager on
ECHO "update ifcfg-eth0"
sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-eth0
sed -i "s/^ONBOOT=.*/ONBOOT=yes/g" /etc/sysconfig/network-scripts/ifcfg-eth0
ECHO "Disable lock cdrom udev rules"
sed -i "/--lock-media/s/^/#/" /usr/lib/udev/rules.d/60-cdrom_id.rules 2>/dev/null>&1
ECHO 'Post set up finished'
%end
