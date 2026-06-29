KVM_TEST_MEDIUM
GRAPHICAL_OR_TEXT
lang en_US
keyboard us
network --bootproto dhcp --hostname atest-guest
rootpw 123456
firewall --enabled --ssh
selinux --enforcing
timezone --utc Asia/Shanghai
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
@standard
@development
python
%end

%post
function ECHO { for TTY in `cat /proc/consoles | awk '{print $NF}'`; do source "/sys/dev/char/$TTY/uevent" && echo "$*" > /dev/$DEVNAME; done }
ECHO "OS install is completed"
grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
dhclient
iptables -F
systemctl mask tmp.mount
selinux --enforcing
sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-eth0
systemctl enable sshd
echo "PermitRootLogin yes" >> /etc/ssh/sshd_config

ECHO 'Post set up finished'
%end
