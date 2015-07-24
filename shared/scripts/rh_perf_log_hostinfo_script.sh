function call() {
    echo "`echo \# $@; eval $@ ; echo \"==>Returned: $?\"`"
    echo
}

echo "==================== Configuration on host ============================="
call hostname

call cat /proc/cmdline

call cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

call lscpu

call "grep flags /proc/cpuinfo |head -n 1"

call numactl --hardware

call "cat /proc/meminfo  |grep HugePages_Total"

call cat /sys/kernel/debug/sched_features

bridges=`brctl show|grep -v "bridge.*name.*bridge.*id"|awk {'print $1'}`
ports=`brctl show|grep -v "bridge.*name.*bridge.*id"|awk {'print $4'}`

for i in $bridges;do
    call echo "ethtool -k $i"
    call ethtool -k $i
done
for i in $ports;do
    call ethtool -k $i
    call ethtool -i $i
    call brctl showstp $i
done

echo "=========================== Test steps ================================="

echo "------------------------- (netperf cmdline) ----------------------------"
grep "Start netperf thread by cmd" $1/../debug.log |sed -e "s/^.*|//"

echo "------------------------- (qemu cmdline) -------------------------------"
grep "Running qemu command" $1/../debug.log -A 1 |sed -e "s/^.*|//"
grep "Running qemu command" $1/../debug.log -A 100|grep "^ *-"

echo "------------------------- (thread pinning) -----------------------------"
grep "pin .* thread(.*) to cpu(.*)" $1/../debug.log -A 1 |sed -e "s/^.*|//"

