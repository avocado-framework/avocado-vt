install
KVM_TEST_MEDIUM
text
lang en_US.UTF-8
langsupport --default=en_US.UTF-8 en_US.UTF-9
keyboard us
network --bootproto dhcp
rootpw 123456
firewall --enabled --ssh
timezone America/New_York
firstboot --disable
bootloader --location=mbr --append="console=tty0 console=ttyS0,115200"
clearpart --all --initlabel
autopart
poweroff
mouse generic3ps/2
skipx

%packages --resolvedeps
@ base
@ development-libs
@ development-tools
gcc
patch
make
nc
ntp
redhat-lsb

%post
function ECHO { for TTY in ttyS0 hvc0; do echo "$*" > /dev/$TTY; done }
ECHO "OS install is completed"
cd home
echo "s0:2345:respawn:/sbin/agetty -L -f /etc/issue 115200 ttyS0 vt100" >> /etc/inittab
echo "ttyS0" >> /etc/securetty
dhclient
chkconfig sshd on
sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-eth0
ECHO 'Post set up finished'
%end
