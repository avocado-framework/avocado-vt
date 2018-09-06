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

call cat /sys/kernel/mm/ksm/run

call sestatus

call cat /proc/sys/kernel/watchdog

call cat /proc/sys/kernel/nmi_watchdog

call tuned-adm active

call tc qdisc show

call ifconfig

bridges=`ip link show type bridge | awk -F':' '/^[0-9]+:\s*\w+\:/{ print $2 }'`
ports=`ip link show type bridge_slave | awk -F':' '/^[0-9]+:\s*\w+\:/{ print $2 }'`

for i in $bridges;do
    call echo "ethtool -k $i"
    call ethtool -k $i
    call ip -d link sh $i
done
for i in $ports;do
    call ethtool -k $i
    call ethtool -i $i
    call ethtool -c $i
done

echo "=========================== Test steps ================================="

echo "------------------------- (netperf cmdline) ----------------------------"
grep "Start netperf thread by cmd" $1/debug.log |sed -e "s/^.*|//"

echo "------------------------- (qemu cmdline) -------------------------------"
grep "Running qemu command" $1/debug.log -A 1 |sed -e "s/^.*|//"
grep "Running qemu command" $1/debug.log -A 100|grep "^ *-"

echo "------------------------- (thread pinning) -----------------------------"
grep "pin .* thread(.*) to cpu(.*)" $1/debug.log -A 1 |sed -e "s/^.*|//"
