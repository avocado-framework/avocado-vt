install
KVM_TEST_MEDIUM
GRAPHICAL_OR_TEXT
reboot
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
part / --fstype=ext4 --grow --asprimary --size=1

%packages --ignoremissing
@minimal-environment
%end

%post
# Output to all consoles defined in /proc/consoles, use "major:minor" as
# device names are unreliable on some platforms
# https://bugzilla.redhat.com/show_bug.cgi?id=1351968
function ECHO { for TTY in `cat /proc/consoles | awk '{print $NF}'`; do source "/sys/dev/char/$TTY/uevent" && echo "$*" > /dev/$DEVNAME; done }
ECHO "OS install is completed"
grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
sed -i -e "s,^GRUB_TIMEOUT=.*,GRUB_TIMEOUT=0," /etc/default/grub
grub2-mkconfig > /etc/grub2.cfg
ECHO 'Post set up finished'
%end
