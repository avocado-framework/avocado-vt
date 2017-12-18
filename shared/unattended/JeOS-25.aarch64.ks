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
part /boot/efi --size=200 --ondisk=sda --fstype=efi
part / --fstype=ext4 --grow --asprimary --size=1

%packages --ignoremissing
gpgme
dmidecode
ethtool
tcpdump
tar
bzip2
pciutils
usbutils
bind-utils
net-tools
rsync
python
-yum-utils
-cryptsetup
-dump
-mlocate
-stunnel
-rng-tools
-ntfs-3g
-sos
-jwhois
-fedora-release-notes
-pam_pkcs11
-wireless-tools
-rdist
-mdadm
-dmraid
-ftp
-system-config-network-tui
-pam_krb5
-nano
-nc
-PackageKit-yum-plugin
-btrfs-progs
-ypbind
-yum-presto
-microcode_ctl
-finger
-krb5-workstation
-ntfsprogs
-iptstate
-fprintd-pam
-irqbalance
-dosfstools
-mcelog
-smartmontools
-lftp
-unzip
-rsh
-telnet
-setuptool
-bash-completion
-pinfo
-rdate
-system-config-firewall-tui
-system-config-firewall-base
-nfs-utils
-words
-cifs-utils
-prelink
-wget
-dos2unix
-passwdqc
-coolkey
-symlinks
-pm-utils
-bridge-utils
-zip
-numactl
-mtr
-sssd
-pcmciautils
-tree
-hunspell
-irda-utils
-time
-man-pages
-yum-langpacks
-talk
-wpa_supplicant
-slang
-authconfig
-newt
-newt-python
-ntsysv
-libnl3
-tcp_wrappers
-quota
-libpipeline
-man-db
-groff
-less
-plymouth-core-libs
-plymouth
-plymouth-scripts
-libgudev1
-ModemManager
-NetworkManager-glib
-selinux-policy
-selinux-policy-targeted
-crontabs
-cronie
-cronie-anacron
-cyrus-sasl
-sendmail
-netxen-firmware
-linux-firmware
-libdaemon
-avahi-autoipd
-libpcap
-ppp
-libsss_sudo
-sudo
-at
-psacct
-parted
-passwd
-tmpwatch
-bc
-acl
-attr
-traceroute
-mailcap
-quota-nls
-mobile-broadband-provider-info
-audit
-e2fsprogs-libs
-e2fsprogs
-biosdevname
-dbus-glib
-libdrm
-setserial
-lsof
-ed
-cyrus-sasl-plain
-dnsmasq
-system-config-firewall-base
-hesiod
-libpciaccess
-policycoreutils
-m4
-checkpolicy
-procmail
-libuser
-polkit
-rsyslog
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
sed -i -e "s,^GRUB_TIMEOUT=.*,GRUB_TIMEOUT=0," /etc/default/grub
grub2-mkconfig > /etc/grub2.cfg
dnf install -y hdparm ntpdate qemu-guest-agent
dnf clean all
mkdir -p /var/log/journal
sed -i -e 's/\#SystemMaxUse=/SystemMaxUse=50M/g' /etc/systemd/journald.conf
dd if=/dev/zero of=/fill-up-file bs=1M
rm -f /fill-up-file
ECHO 'Post set up finished'
%end
