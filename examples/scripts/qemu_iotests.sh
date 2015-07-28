#!/bin/bash

TEST_IMG=$1

### regression function definition ###
function regression() {

    # Nolan I (incorrectly reports free clusters)
    $QEMU_IMG create -f qcow2 $TEST_IMG 6G
    $QEMU_IO <<EOF
write 2048k 4k -P 65
write 4k 4k
write 9M 4k
read 2044k 8k -P 65
EOF
    #FIXME: should use `$QEMU_IMG check $TEST_IMG` when the following
    # bugs fixed:
    # Bug 658753 - wrong file format when " qemu-img info " on lvm
    $QEMU_IMG check -f qcow2 $TEST_IMG

    # Nolan II (wrong used cluster)
    $QEMU_IMG create -f qcow2 $TEST_IMG 6G
    $QEMU_IO <<EOF
write 2048k 4k -P 165
write 64k 4k
write 9M 4k
write 2044k 4k -P 165
write 8M 4k -P 99
read -P 165 2044k 8k
EOF
    $QEMU_IMG check -f qcow2 $TEST_IMG

    # Jason Wang (Regression for BZ#598407)
    $QEMU_IMG create -f qcow2 -ocluster_size=512 $TEST_IMG 1G
    $QEMU_IO <<EOF
write -b 0 64M
EOF
    $QEMU_IMG check -f qcow2 $TEST_IMG

    # Avi (AIO allocation on the same cluster)

    $QEMU_IMG create -f qcow2 $TEST_IMG 6G
    for i in $(seq 1 10); do
        off1=$(( i * 1024 * 1024 ))
        off2=$(( i * 1024 * 1024 + 512 ))
        $QEMU_IO <<EOF
aio_write $off1 1M
aio_write $off2 1M
EOF
    done
    $QEMU_IMG check -f qcow2 $TEST_IMG


    # More AIO

    $QEMU_IMG create -f qcow2 $TEST_IMG 6G
    for i in $(seq 1 10); do
        off1=$(( i * 1024 * 1024 ))
        off2=$(( i * 1024 * 1024 + 512 ))
        off3=$(( (i + 1) * 1024 * 1024 ))
        $QEMU_IO <<EOF
aio_write $off1 1M -P 99
aio_write $off2 1M -P 123
EOF
        $QEMU_IO <<EOF
read $off1 512 -P 99
read $off3 512 -P 123
EOF
        $QEMU_IO <<EOF
aio_write $off2 1M -P 88
aio_write $off1 1M -P 234
EOF
        $QEMU_IO <<EOF
read $off3 512 -P 88
read $off1 512 -P 234
EOF
    done
    $QEMU_IMG check -f qcow2 $TEST_IMG

    $QEMU_IMG create -f qcow2 $TEST_IMG 6G
    for i in $(seq 1 10); do
        off1=$(( i * 1024 * 1024 ))
        off2=$(( i * 1024 * 1024 + 4096 ))
        off3=$(( (i + 1) * 1024 * 1024 ))
        $QEMU_IO <<EOF
aio_write $off1 1M -P 99
aio_write $off2 1M -P 123
EOF
        $QEMU_IO <<EOF
read $off1 512 -P 99
read $off3 512 -P 123
EOF
        $QEMU_IO <<EOF
aio_write $off2 1M -P 88
aio_write $off1 1M -P 234
EOF
        $QEMU_IO <<EOF
read $off3 512 -P 88
read $off1 512 -P 234
EOF
    done
    $QEMU_IMG check -f qcow2 $TEST_IMG

    # bug 635354 by Feng Yang
    $QEMU_IMG create -f raw $TEST_IMG 6G
    $QEMU_IMG create -F raw -f qcow2 -b $TEST_IMG /tmp/$(basename $TEST_IMG).snapshot
    $QEMU_IO <<EOF
write 0 512k -P 3
EOF
    $QEMU_IMG commit /tmp/$(basename $TEST_IMG).snapshot

    # Bug 558195
    $QEMU_IMG create -f qcow2 test.qcow2 6G
    $QEMU_IO <<EOF
write 2M 4M -P 65
EOF
    $QEMU_IMG check -f qcow2 test.qcow2
    mv test.qcow2 backing.qcow2

    $QEMU_IMG create -f qcow2 -b backing.qcow2 test.qcow2
    $QEMU_IO <<EOF
write 4M 4M -P 97
EOF
    $QEMU_IMG check -f qcow2 test.qcow2
    mv test.qcow2 overlay.qcow2

    $QEMU_IMG convert -f qcow2 overlay.qcow2 -O qcow2 test.qcow2
    $QEMU_IO <<EOF
read 2M 2M -P 65
read 4M 4M -P 97
EOF
    $QEMU_IMG check -f qcow2 test.qcow2
}


########### implement the qemu-io test ############

QEMU_PATH="/usr/bin"
QEMU_IMG="$QEMU_PATH/qemu-img"
QEMU_IO="$QEMU_PATH/qemu-io "$TEST_IMG


TEST_OFFSETS="0 4294967296"
# TEST_OPS="writev read write readv aio_write readv"
TEST_OPS="read write"

function io_pattern() {
    local op=$1
    local start=$2
    local size=$3
    local step=$4
    local count=$5
    local pattern=$6

    echo === IO: pattern $pattern >&2
    for i in $(seq 1 $count); do
        echo $op -P $pattern $(( start + i * step )) $size
    done
}

function io() {
    local start=$2
    local pattern=$(( (start >> 9) % 256 ))

    io_pattern $@ $pattern
}

function io_zero() {
    io_pattern $@ 0
}

function io_test() {
    local orig_offset=$1

    for op in $TEST_OPS; do

        offset=$orig_offset

        # Complete clusters (size = 4k)
        io $op $offset 4096 4096 256 | $QEMU_IO
        offset=$((offset + 256 * 4096))

        # From somewhere in the middle to the end of a cluster
        io $op $((offset + 2048)) 2048 4096 256 | $QEMU_IO
        offset=$((offset + 256 * 4096))

        # From the start to somewhere in the middle of a cluster
        io $op $offset 2048 4096 256 | $QEMU_IO
        offset=$((offset + 256 * 4096))

        # Completely misaligned (and small)
        io $op $((offset + 1024)) 2048 4096 256 | $QEMU_IO
        offset=$((offset + 256 * 4096))

        # Spanning multiple clusters
        io $op $((offset + 2048)) 8192 12288 64 | $QEMU_IO
        offset=$((offset + 64 * 12288))

        # Spanning multiple L2 tables
        # L2 table size: 512 clusters of 4k = 2M
        io $op $((offset + 2048)) 4194304 4999680 8 | $QEMU_IO
        offset=$((offset + 8 * 4999680))
if false; then
    true
fi
    done
}

function io_test2() {
    local orig_offset=$1

    # Pattern (repeat after 9 clusters):
    # used - used - free - used - compressed - compressed - free - free - compressed

    # Write the clusters to be compressed
    echo === Clusters to be compressed [1]
    io_pattern writev $((offset + 4 * 4096)) 4096 $((9 * 4096)) 256 165 | $QEMU_IO
    echo === Clusters to be compressed [2]
    io_pattern writev $((offset + 5 * 4096)) 4096 $((9 * 4096)) 256 165 | $QEMU_IO
    echo === Clusters to be compressed [3]
    io_pattern writev $((offset + 8 * 4096)) 4096 $((9 * 4096)) 256 165 | $QEMU_IO

    mv /tmp/test.qcow2 /tmp/test.orig
    $QEMU_IMG convert -f qcow2 -O qcow2 -c /tmp/test.orig /tmp/test.qcow2

    # Write the used clusters
    echo === Used clusters [1]
    io_pattern writev $((offset + 0 * 4096)) 4096 $((9 * 4096)) 256 165 | $QEMU_IO
    echo === Used clusters [2]
    io_pattern writev $((offset + 1 * 4096)) 4096 $((9 * 4096)) 256 165 | $QEMU_IO
    echo === Used clusters [3]
    io_pattern writev $((offset + 3 * 4096)) 4096 $((9 * 4096)) 256 165 | $QEMU_IO

    # Read them
    echo === Read used/compressed clusters
    io_pattern readv $((offset + 0 * 4096)) $((2 * 4096)) $((9 * 4096)) 256 165 | $QEMU_IO
    io_pattern readv $((offset + 3 * 4096)) $((3 * 4096)) $((9 * 4096)) 256 165 | $QEMU_IO
    io_pattern readv $((offset + 8 * 4096)) $((1 * 4096)) $((9 * 4096)) 256 165 | $QEMU_IO

    echo === Read zeros
    io_zero readv $((offset + 2 * 4096)) $((1 * 4096)) $((9 * 4096)) 256 | $QEMU_IO
    io_zero readv $((offset + 6 * 4096)) $((2 * 4096)) $((9 * 4096)) 256 | $QEMU_IO

    # TODO Overwrite ranges containing multiple cluster types
}

# What needs to be checked?
# - Images > 4 GB to avoid 32 bit truncation
# - With backing file and without
# - Compressed image, non-compressed image, images with both compressed and
#   non-compressed clusters
# - Encrypted image
# - Read/Write operations...
#   * ...on exactly one cluster (start - end)
#   * ...on parts of one cluster (start offset, end offset, both)
#   * ...spanning multiple clusters
#   * ...spanning clusters of multiple L2 tables
# - Snapshots (especially wrt refcounting)
#   * copied clusters vs. cow clusters
# - AIO
#   * Concurrent overlapping writes

# Run regression tests first
regression

#exit

# Empty image
$QEMU_IMG create -f qcow2 $TEST_IMG 6G
for offset in $TEST_OFFSETS; do
    io_test $offset
    echo With offset $offset
    $QEMU_IMG check -f qcow2 $TEST_IMG
done

# Compressed image
$QEMU_IMG create -f qcow2 /tmp/test.orig 6G
$QEMU_IMG convert -f qcow2 -O qcow2 -c /tmp/test.orig $TEST_IMG
ORIG_TEST_OPS="$TEST_OPS"
#TEST_OPS="read readv"
TEST_OPS="read"
for offset in $TEST_OFFSETS; do
    io_test $offset
    echo test1: With offset $offset
    $QEMU_IMG check -f qcow2 $TEST_IMG
done
TEST_OPS="$ORIG_TEST_OPS"
for offset in $TEST_OFFSETS; do
    # Some odd offset (1 sector), so tests will write to areas occupied partly
    # by old (compressed) data and empty clusters
    offset=$((offset + 512))
    io_test $offset
    echo With offset $offset
    $QEMU_IMG check -f qcow2 /$TEST_IMG
done
if false; then
	true
fi

# More interesting patterns
#$QEMU_IMG create -f qcow2 /tmp/test.qcow2 6G
#for offset in $TEST_OFFSETS; do
#    io_test2 $offset
#    echo test2: With offset $offset
#    $QEMU_IMG check -f qcow2 /tmp/test.qcow2
#done


#exit

# TODO Combine backing store and COW image

# With snapshots
for i in $(seq 1 3); do
    $QEMU_IMG snapshot -c /tmp/test$i $TEST_IMG
    for offset in $TEST_OFFSETS; do
        io_test $offset
        echo With snapshot test$i, offset $offset
        $QEMU_IMG check -f qcow2 $TEST_IMG
    done
done
