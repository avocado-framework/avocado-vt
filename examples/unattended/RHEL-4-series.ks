install
KVM_TEST_MEDIUM
text
lang en_US.UTF-8
langsupport --default=en_US.UTF-8 en_US.UTF-9
keyboard us
network --bootproto dhcp
rootpw 123456
firewall --enabled --ssh
selinux --enforcing
timezone --utc America/New_York
firstboot --disable
bootloader --location=mbr --append="console=tty0 console=ttyS0,115200"
zerombr
clearpart --all --initlabel
autopart
poweroff

%packages
@ base
@development-libs
@development-tools
gcc4
gcc4-gfortran
patch
make
nc
ntp
redhat-lsb

%post
function ECHO { for TTY in ttyS0 hvc0; do echo "$*" > /dev/$TTY; done }
ECHO "OS install is completed"
grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
grubby --args="divider=10" --update-kernel=$(grubby --default-kernel)
cd home
dhclient
chkconfig sshd on
iptables -F
echo 0 > selinux/enforce
sed -i '/^HWADDR/d' /etc/sysconfig/network-scripts/ifcfg-eth0
echo "s0:2345:respawn:/sbin/agetty -L -f /etc/issue 115200 ttyS0 vt100" >> /etc/inittab
echo "ttyS0" >> /etc/securetty
wget http://www.python.org/ftp/python/2.6.6/Python-2.6.6.tar.bz2
tar xjf Python-2.6.6.tar.bz2
cd Python-2.6.6
./configure --prefix=/usr/local --exec-prefix=/usr/local
make
make install
ln -sf /usr/local/bin/python /usr/bin/python
sleep 10
ECHO 'Post set up finished'
%end
