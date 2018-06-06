install
KVM_TEST_MEDIUM
GRAPHICAL_OR_TEXT
lang en_US
keyboard us
network --bootproto dhcp --hostname atest-guest
rootpw 123456
firewall --enabled --ssh
selinux --enforcing
timezone --utc America/New_York
firstboot --disable
bootloader --location=mbr --append="console=tty0 console=ttyS0,115200"
zerombr
poweroff
KVM_TEST_LOGGING

clearpart --all --initlabel
autopart

%packages --ignoremissing
@standard
@c-development
@development-tools
python
net-tools
sg3_utils
%end

%post
# FIXME: Remove the /dev/ttysclp0 workaround when s390x console bug is resolved
# https://bugzilla.redhat.com/show_bug.cgi?id=1351968
function ECHO { for TTY in `[ -e /dev/ttysclp0 ] && echo ttysclp0; cat /proc/consoles | cut -f1 -d' '`; do echo "$*" > /dev/$TTY; done }
ECHO "OS install is completed"
grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
dhclient
chkconfig sshd on
iptables -F
systemctl mask tmp.mount
echo 0 > /selinux/enforce
sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-eth0
# if package groups were missing from main installation repo
# try again from installed system
dnf -y groupinstall c-development development-tools
# include avocado: allows using this machine with remote runner
dnf -y install python2-avocado
ECHO 'Post set up finished'
%end
