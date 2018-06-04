#!/bin/sh
# usage sh pktgen.sh $dst_ip $dst_mac $device $queues
if [ $# -ne 4 ]
then
    echo "Error, pktgen.sh need four params"
    echo 'Usage: pktgen.sh <dst_ip> <dst_mac> <device> <queues>'
    exit 1
fi
DST_IP=$1
DST_MAC=$2
NET_DEVICE=$3
QUEUES=$4


lsmod | grep pktgen || modprobe  pktgen
echo reset > /proc/net/pktgen/pgctrl
ifconfig $NET_DEVICE up

function pgset() {
    local result
    echo $1 > $PGDEV
    result=`cat $PGDEV | fgrep "Result: OK:"`
    if [ "$result" = "" ]; then
         cat $PGDEV | fgrep Result:
    fi
}


function pg() {
    echo inject > $PGDEV
    cat $PGDEV
}


for i in 0 `seq $(($QUEUES-1))`
do
    echo "Adding queue $i of $NET_DEVICE"
    dev=$NET_DEVICE@$i
    PGDEV=/proc/net/pktgen/kpktgend_$i
    pgset "rem_device_all"
    pgset "add_device $dev"
    pgset "max_before_softirq 100000"

    # Configure the individual devices
    echo "Configuring devices $dev"
    PGDEV=/proc/net/pktgen/$dev

    pgset "queue_map_min $i"
    pgset "queue_map_max $i"
    pgset "count 10000000"
    pgset "min_pkt_size 60"
    pgset "max_pkt_size 60"
    pgset "dst $DST_IP"
    pgset "dst_mac $DST_MAC"
    pgset "udp_src_min 0"
    pgset "udp_src_max 65535"
    pgset "udp_dst_min 0"
    pgset "udp_dst_max 65535"
done


# Time to run
PGDEV=/proc/net/pktgen/pgctrl
echo "Running... ctrl^C to stop"
pgset "start"
echo "Done"


for i in "/proc/net/pktgen/$NET_DEVICE@"*
do
    cat $i | tail -n 1
done


for i in "/proc/net/pktgen/$NET_DEVICE@"*
do
    grep cur_queue_map $i
done
