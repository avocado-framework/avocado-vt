#!/bin/sh
# usage sh pktgen.sh $dst $device $queues $size

DST=$1
NET_DEVICE=$2
QUEUES=$3
SIZE=$4

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

for i in 0 `seq $(($QUEUES-1))`
do
    echo "Adding queue 0 of $1"
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
    pgset "count 0"
    pgset "min_pkt_size $SIZE"
    pgset "max_pkt_size $SIZE"
    echo $DST | grep ":"
    if [ $? -eq 0 ]
    then
        pgset "dst_mac $DST"
    else
        pgset "dst $DST"
    fi
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
