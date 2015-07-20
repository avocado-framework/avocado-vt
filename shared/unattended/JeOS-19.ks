install
KVM_TEST_MEDIUM
text
lang en_US.UTF-8
keyboard us
network --onboot yes --device eth0 --bootproto dhcp --noipv6 --hostname atest-guest
rootpw 123456
firewall --disabled
selinux --disabled
timezone --utc America/New_York
firstboot --disable
bootloader --location=mbr --timeout=0 --append="console=tty0 console=ttyS0,115200 plymouth.enable=0"
zerombr
poweroff
services --enabled network
repo --name updates
KVM_TEST_LOGGING

clearpart --all --initlabel
part / --fstype=ext4 --grow --asprimary --size=1

%packages
gpgme
hardlink
dmidecode
ethtool
tcpdump
tar
bzip2
pciutils
usbutils
net-tools
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
-rsync
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
-diffutils
-policycoreutils
-m4
-checkpolicy
-procmail
-libuser
-polkit
-rsyslog
%end

%post
function ECHO { for TTY in `cat /proc/consoles | cut -f1 -d' '`; do echo "$*" > /dev/$TTY; done }
grubby --remove-args="rhgb quiet" --update-kernel=$(grubby --default-kernel)
echo 0 > /selinux/enforce
sed -i "/^HWADDR/d" /etc/sysconfig/network-scripts/ifcfg-eth0
systemctl enable sshd.service
systemctl mask fedora-wait-storage.service
systemctl mask fedora-storage-init-late.service
systemctl mask fedora-storage-init.service
systemctl mask fedora-autoswap.service
systemctl mask fedora-configure.service
systemctl mask fedora-loadmodules.service
systemctl mask fedora-readonly.service
systemctl mask systemd-readahead-collect.service
systemctl mask plymouth-start.service
systemctl mask network.service
systemctl mask remote-fs.target
systemctl mask cryptsetup.target
systemctl mask sys-devices-virtual-tty-tty2.device
systemctl mask sys-devices-virtual-tty-tty3.device
systemctl mask sys-devices-virtual-tty-tty4.device
systemctl mask sys-devices-virtual-tty-tty5.device
systemctl mask sys-devices-virtual-tty-tty6.device
systemctl mask sys-devices-virtual-tty-tty7.device
systemctl mask sys-devices-virtual-tty-tty8.device
systemctl mask sys-devices-virtual-tty-tty9.device
systemctl mask sys-devices-virtual-tty-tty10.device
systemctl mask sys-devices-virtual-tty-tty11.device
systemctl mask sys-devices-virtual-tty-tty12.device
yum install -y hdparm ntpdate qemu-guest-agent
yum clean all
mkdir -p /var/log/journal
dd if=/dev/zero of=/fill-up-file bs=1M
rm -f /fill-up-file
ECHO 'Post set up finished'
ECHO "OS install is completed"
%end
