function call() {
    echo "`echo \# $@; eval $@ ; echo \"==>Returned: $?\"`"
    echo
}

echo
echo "==================== Configuration on guest ============================"

call cat /proc/cmdline

call cat /sys/devices/system/clocksource/clocksource0/current_clocksource

call "grep flags /proc/cpuinfo |head -n 1"
