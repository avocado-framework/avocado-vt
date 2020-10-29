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
# Additional repositories could be specified in 'kickstart_extra_repos' parameter
KVM_TEST_REPOS

%packages --ignoremissing
@c-development
@development-tools
net-tools
sg3_utils
# include avocado: allows using this machine with remote runner
python3-avocado
%end

%post
# Output to all consoles defined in /proc/consoles, use "major:minor" as
# device names are unreliable on some platforms
# https://bugzilla.redhat.com/show_bug.cgi?id=1351968
function ECHO { for TTY in `cat /proc/consoles | awk '{print $NF}'`; do source "/sys/dev/char/$TTY/uevent" && echo "$*" > /dev/$DEVNAME; done }
ECHO "OS install is completed"
grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
dhclient
iptables -F
systemctl mask tmp.mount
selinux --enforcing
sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-eth0
# if packages were missing from main installation repo
# try again from installed system
dnf -y groupinstall c-development development-tools
dnf -y install net-tools sg3_utils python3-avocado
systemctl enable sshd
#From fedora31,root login is disabled by default,we need enable it for our test
echo "PermitRootLogin yes" >> /etc/ssh/sshd_config

ECHO 'Post set up finished'
%end
