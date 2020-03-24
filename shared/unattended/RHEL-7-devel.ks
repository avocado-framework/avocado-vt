install
KVM_TEST_MEDIUM
GRAPHICAL_OR_TEXT
poweroff
lang en_US.UTF-8
keyboard us
network --onboot yes --device eth0 --bootproto dhcp
rootpw --plaintext 123456
firstboot --disable
user --name=test --password=123456
firewall --enabled --ssh
selinux --enforcing
timezone --utc America/New_York
bootloader --location=mbr --append="console=tty0 console=ttyS0,115200"
zerombr
KVM_TEST_LOGGING
clearpart --all --initlabel
autopart
xconfig --startxonboot
# Additional repositories could be specified in 'kickstart_extra_repos' parameter
KVM_TEST_REPOS

%packages --ignoremissing
@base
@core
@development
@additional-devel
@debugging
@network-tools
@x11
@gnome-desktop
@fonts
@smart-card
gnome-utils
python-imaging
python-six
pyparsing
net-tools
NetworkManager
ntpdate
dconf
watchdog
coreutils
usbutils
spice-xpi
spice-gtk3
docbook-utils
sgml-common
openjade
virt-viewer
pulseaudio-libs-devel
mesa-libGL-devel
pygtk2-devel
libjpeg-turbo-devel
spice-vdagent
usbredir
SDL
totem
dmidecode
alsa-utils
sg3_utils
-gnome-initial-setup
%end

%post
# Output to all consoles defined in /proc/consoles, use "major:minor" as
# device names are unreliable on some platforms
# https://bugzilla.redhat.com/show_bug.cgi?id=1351968
function ECHO { for TTY in `cat /proc/consoles | awk '{print $NF}'`; do source "/sys/dev/char/$TTY/uevent" && echo "$*" > /dev/$DEVNAME; done }
ECHO "OS install is completed"
ECHO "remove rhgb quiet by grubby"
grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
ECHO "dhclient"
dhclient
ECHO "chkconfig sshd on"
chkconfig sshd on
ECHO "iptables -F"
iptables -F
ECHO "echo 0 > selinux/enforce"
echo 0 > /selinux/enforce
ECHO "chkconfig NetworkManager on"
chkconfig NetworkManager on
ECHO "update ifcfg-eth0"
sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-eth0
ECHO "Disable lock cdrom udev rules"
sed -i "/--lock-media/s/^/#/" /usr/lib/udev/rules.d/60-cdrom_id.rules 2>/dev/null>&1
#Workaround for graphical boot as anaconda seems to always instert skipx
systemctl set-default graphical.target
sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-*
sed -i "s/ONBOOT=no/ONBOOT=yes/" /etc/sysconfig/network-scripts/ifcfg-*
cat > '/etc/gdm/custom.conf' << EOF
[daemon]
AutomaticLogin=test
AutomaticLoginEnable=True
EOF
cat >> '/etc/sudoers' << EOF
test ALL = NOPASSWD: /sbin/shutdown -r now,/sbin/shutdown -h now
EOF
cat >> '/home/test/.bashrc' << EOF
alias shutdown='sudo shutdown'
EOF
ECHO 'Post set up finished'
%end
