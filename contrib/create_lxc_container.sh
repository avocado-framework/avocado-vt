#!/bin/bash
set -eu

# Minimal sample container creation script:
# -----------------------------------------
# Part 1 of this script provides minimal viable LXC container with networking
# Part 2 of this script provides locally installed Avocado dependencies
#
# Example usage to run VT boot tests on a container nested inside another container:
# $ cd $AVOCADO_VT_REPO_DIR  # assuming locally installed Avocado VT source
# $ CID=c200 LXCROOT=/mnt/local/images DEPTH=1 bash contrib/create_lxc_container.sh
# $ avocado run --status-server-disable-auto --spawner=lxc boot

# minimal configuration
readonly cid="${CID:-c100}"
readonly dist="${DIST:-fedora}"
readonly release="${RELEASE:-36}"
readonly arch="${ARCH:-amd64}"
readonly sshpass="${SSHPASS:-test1234}"
readonly lxcroot="${LXCROOT:-/var/lib/lxc}"
readonly netmode="${NETMODE:-0}"
# depth in case of nested container creation (affecting container net octets)
readonly depth="${DEPTH:-0}"
readonly depth_octet="$((255 - depth))"

readonly containerfs="$lxcroot/$cid/rootfs"
readonly containercfg="$lxcroot/$cid/config"

echo "Creating vanilla container ${cid}"
dnf install -y lxc lxc-templates
lxc-create -t download -n $cid -- --dist $dist --release $release --arch $arch

echo "Setting root password for ${cid}"
chroot $containerfs /bin/bash -c "echo \"$sshpass\" | passwd --stdin root"

echo "Providing static IP configuration (to avoid having to setup DHCP servers)"
octet=$(echo "$cid" | tr -d ' ' | sed -E "s/c([0-9]+)/\1/g")
cat <<- EOF >> $containercfg
# Additional network configuration
lxc.net.0.ipv4.address = 192.168.$depth_octet.$octet/24
lxc.net.0.ipv4.gateway = 192.168.$depth_octet.254
EOF

# disable the systemd-networkd service while the container is offline to
# make sure it doesn't override the static IP settings from LXC
rm -f $containerfs/etc/systemd/system/network-online.target.wants/systemd-networkd-wait-online.service
rm -f $containerfs/etc/systemd/system/multi-user.target.wants/systemd-networkd.service
rm -f $containerfs/etc/systemd/system/sockets.target.wants/systemd-networkd.socket
rm -f $containerfs/etc/systemd/system/dbus-org.freedesktop.network1.service

echo "Setting default bridge for this and all future containers (or skip if available)"
if [ $netmode -eq 0 ]; then
    ip addr show dev lxcbr0 > /dev/null
elif [ $netmode -eq 1 ]; then
    dnf install -y net-tools bind-utils bridge-utils openssh-server
    brctl addbr lxcbr0
    ip addr add 192.168.$depth_octet.254/24 dev lxcbr0
    ip link set lxcbr0 up
else
    nmcli connection add type bridge ifname lxcbr0 con-name br0 ipv4.method manual ipv4.addresses "192.168.$depth_octet.254/24"
    nmcli connection up lxcbr0
fi

echo "Setting NAT to provide internet access"
dnf install -y firewalld
systemctl start firewalld
firewall-cmd --permanent --zone=external --change-interface=lxcbr0
firewall-cmd --permanent --zone=external --change-interface=eth0
firewall-cmd --permanent --zone=external --add-port=8080/tcp
# NOTE: possible stricter rule derived from iptables but not really working
#firewall-cmd --permanent --direct --add-rule ipv4 filter FORWARD 0 -s 192.168.$depth_octet.0/24 -i lxcbr0 -j ACCEPT
firewall-cmd --reload

echo "Setting DNS server (unfortunately not available by default)"
dns_server=9.9.9.9
sed -i "s/#DNS=/DNS=$dns_server/" $containerfs/etc/systemd/resolved.conf

# these devices are needed for Avocado VT
# rtc
echo "lxc.cgroup2.devices.allow = b 252:* rwm" >> $containercfg
# device-mapper
echo "lxc.cgroup2.devices.allow = b 253:* rwm" >> $containercfg
# tun
# or temporary fix on container: mkdir /dev/net; mknod /dev/net/tun c 10 200
echo "lxc.cgroup2.devices.allow = c 10:200 rwm" >> $containercfg
echo "lxc.mount.entry = /dev/net/tun dev/net/tun none bind,create=file 0 0" >> $containercfg
# kvm
# or temporary fix on container: mknod /dev/kvm c 10 232
echo "lxc.cgroup2.devices.allow = c 10:232 rwm" >> $containercfg
echo "lxc.mount.entry = /dev/kvm dev/kvm none bind,create=file 0 0" >> $containercfg

# mount results folder needed for all avocado runs
echo "lxc.mount.entry = /root/avocado/job-results/ root/avocado/job-results/ none rw,bind,create=dir 0 0" >> $containercfg

echo "Starting container ${cid} environment around the current repo"
echo "lxc.mount.entry = $(pwd) root/avocado-vt none rw,bind,create=dir 0 0" >> $containercfg
lxc-start $cid
# networking has to be established within a few seconds
sleep 10

echo "Installing all avocado dependencies"
lxc-attach -n $cid -- bash -eu <<- HERE
cd /root

dnf install -y net-tools bind-utils openssh-server
echo "PermitRootLogin yes" >> /etc/ssh/sshd_config
systemctl enable sshd.service && systemctl start sshd.service
# TODO: some of our vms do not support newest SFTP used by SCP
mv /usr/bin/scp /usr/bin/scp.orig
echo $'scp.orig -O \044\052' > /usr/bin/scp
chmod a+x /usr/bin/scp

dnf install -y git pip python-wheel

echo "Installing most up-to-date Aexpect dependency in develop mode"
git clone --depth 1 https://github.com/avocado-framework/aexpect.git aexpect-libs
cd aexpect-libs
pip install -e .
cd ..

echo "Installing most up-to-date Avocado dependency in develop mode"
git clone --depth 1 https://github.com/avocado-framework/avocado.git avocado-libs
cd avocado-libs
pip install -e .
cd ..

# additional binary dependencies for Avocado VT
dnf install -y gcc python3-devel nc tcpdump
# supposedly optional binary dependencies for Avocado VT
dnf install -y qemu-kvm qemu-img python-pillow libvirt libvirt-client
# TODO: supposedly optional service for Avocado VT (missing bridge for pure Qemu VMs)
systemctl start libvirtd

echo "Installing current Avocado VT plugin in develop mode"
cd avocado-vt
pip install -e .
cd ..

echo "Bootstrapping Avocado VT"
avocado vt-bootstrap --yes-to-all

echo "Done installing all Avocado sources in develop mode"
HERE

echo
echo "Configure avocado to use the container"
mkdir -p /etc/avocado
cat> /etc/avocado/avocado.conf <<EOF
[run]
# LXC and remote spawners require manual status server address
status_server_uri = 192.168.$depth_octet.254:8080
status_server_listen = 192.168.$depth_octet.254:8080

[spawner.lxc]
slots = ['$cid']
EOF

echo
echo "Container created successfully"
