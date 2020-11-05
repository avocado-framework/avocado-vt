#!/bin/bash
# @author Amos Kong <akong@redhat.com>
# @copyright: 2012 Red Hat, Inc.
#
# This script is prepared for RHEL/Fedora system, it's just an
# example, users can reference it to custom their own script.

if [[ $# != 2 ]];then
    echo "usage: $0 <guest/host> <rebooted/none>"
    exit
fi
guest=$1
reboot=$2

all_services='abrtd acpid anacron atd auditd autofs avahi-daemon bluetooth collectd cpuspeed crond cups haldaemon hidd ip6tables isdn kdump koan kudzu libvirt-guests lvm2-monitor mcstrans mdmonitor messagebus netfs ntpdate openibd opensmd portreserve postfix qpidd restorecond rhnsd rhsmcertd rpcgssd rpcidmapd sendmail setroubleshoot smartd tuned xfs yum-updatesd'

########################
echo "Setup env for performance testing, reboot isn't needed"
####
echo "Run test on a private LAN, as there are multpile nics, so set arp_filter to 1"
sysctl net.ipv4.conf.default.arp_filter=1
sysctl net.ipv4.conf.all.arp_filter=1
echo "Disable netfilter on bridges"
ip link set switch type bridge nf_call_iptables 0
ip link set switch type bridge nf_call_ip6tables 0
ip link set switch type bridge nf_call_arptables 0
echo "Set bridge forward delay to 0"
ip link set switch type bridge forward_delay 0

####
echo "Stop the running serivices"

if [[ $guest = "host" ]];then
    echo "Run tunning profile on host"
    # RHEL6, requst 'tuned' package
    tuned-adm profile enterprise-storage
    # RHEL5
    service tuned start
fi

for i in $all_services;do
    service $i stop
done
########################

if [[ $reboot = "rebooted" ]];then
    echo "OS already rebooted"
    echo "Environment setup finished"
    exit
fi

########################
echo "Setup env for performance testing, reboot is needed"
####
echo "Setup runlevel to 3"
if [[ $guest = "guest" ]];then
   iptables -F
   service iptables stop
   chkconfig iptables off
   echo sed -ie "s/id:.*:initdefault:/id:3:initdefault:/g"  /etc/inittab
fi

####
echo "Off services when host starts up"

echo "SELINUX=disabled" >> /etc/selinux/config

for i in $all_services;do
    chkconfig $i off
done

########################
echo "Environment setup finished"
echo "OS should reboot"
