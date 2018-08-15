===================
Performance Testing
===================

Performance subtests
====================

network
-------

- `netperf (linux and windows) <https://github.com/autotest/autotest/tree/master/client/virt/tests/netperf.py>`_
- `ntttcp (windows) <https://github.com/autotest/autotest/tree/master/client/virt/tests/ntttcp.py>`_

block
-----

- `iozone (linux) <https://github.com/autotest/virt-test/virttest/iozone>`_
- iozone (windows) (iozone has its own result analysis module)
- iometer (windows) (not push upstream)
- `ffsb (linux) <https://github.com/autotest/virt-test/virttest/ffsb>`_
- `qemu_iotests (host) <https://github.com/autotest/autotest-client-tests/tree/master/qemu_iotests>`_
- `fio (linux) <https://github.com/autotest/autotest-client-tests/tree/master/fio>`_

Environment setup
=================

  Autotest already supports prepare environment for performance testing, guest/host need to be reboot for some configuration.
  `setup script <https://github.com/autotest/virt-test/blob/master/shared/scripts/rh_perf_envsetup.sh>`_

Autotest supports to numa pining. Assign "numanode=-1" in tests.cfg, then vcpu threads/vhost_net threads/VM memory will be pined to last numa node. If you want to pin other processes to numa node, you can use numctl and taskset.

::

  memory:
  $ numactl -m $n $cmdline
  cpu:
  $ taskset $node_mask $thread_id

The following content is manual guide.

::

  1.First level pinning would be to use numa pinning when starting the guest.
  e.g.  $ numactl -c 1 -m 1 qemu-kvm  -smp 2 -m 4G <> (pinning guest memory and cpus to numa-node 1)

  2.For a single instance test, it would suggest trying a one to one mapping of vcpu to pyhsical core.
  e.g.
  get guest vcpu threads id
  $ taskset -p 40 $vcpus1  #(pinning vcpu1 thread to pyshical cpu #6 )
  $ taskset -p 80 $vcpus2  #(pinning vcpu2 thread to physical cpu #7 )

  3.To pin vhost on host. get vhost PID and then use taskset to pin it on the same soket.
  e.g
  $ taskset -p 20 $vhost #(pinning vcpu2 thread to physical cpu #5 )

  4.In guest,pin the IRQ to one core and the netperf to another.
  1) make sure irqbalance is off - `$ service irqbalance stop`
  2) find the interrupts - `$ cat /proc/interrupts`
  3) find the affinity mask for the interrupt(s) - `$ cat /proc/irq/<irq#>/smp_affinity`
  4) change the value to match the proper core.make sure the vlaue is cpu mask.
  e.g. pin the IRQ to first core.
     $ echo 01>/proc/irq/$virti0-input/smp_affinity
     $ echo 01>/proc/irq/$virti0-output/smp_affinity
  5)pin the netserver to another core.
  e.g.
  $ taskset -p 02 netserver

  5.For host to guest scenario. to get maximum performance. make sure to run netperf on different cores on the same numa node as the guest.
  e.g.
  $ numactl -m 1 netperf -T 4 (pinning netperf to physical cpu #4)

Execute testing
===============

- Submit jobs in Autotest server, only execute netperf.guset_exhost for three times.

``tests.cfg``:

::

  only netperf.guest_exhost
  variants:
      - repeat1:
      - repeat2:
      - repeat3:
  # vbr0 has a static ip: 192.168.100.16
  bridge=vbr0
  # virbr0 is created by libvirtd, guest nic2 get ip by dhcp
  bridge_nic2 = virbr0
  # guest nic1 static ip
  ip_nic1 = 192.168.100.21
  # external host static ip:
  client = 192.168.100.15


Result files:

::

  $ cd /usr/local/autotest/results/8-debug_user/192.168.122.1/
  $ find .|grep RHS
  kvm.repeat1.r61.virtio_blk.smp2.virtio_net.RHEL.6.1.x86_64.netperf.exhost_guest/results/netperf-result.RHS
  kvm.repeat2.r61.virtio_blk.smp2.virtio_net.RHEL.6.1.x86_64.netperf.exhost_guest/results/netperf-result.RHS
  kvm.repeat3.r61.virtio_blk.smp2.virtio_net.RHEL.6.1.x86_64.netperf.exhost_guest/results/netperf-result.RHS

- Submit same job in another env (different packages) with same configuration

Result files:

::

  $ cd /usr/local/autotest/results/9-debug_user/192.168.122.1/
  $ find .|grep RHS
  kvm.repeat1.r61.virtio_blk.smp2.virtio_net.RHEL.6.1.x86_64.netperf.exhost_guest/results/netperf-result.RHS
  kvm.repeat2.r61.virtio_blk.smp2.virtio_net.RHEL.6.1.x86_64.netperf.exhost_guest/results/netperf-result.RHS
  kvm.repeat3.r61.virtio_blk.smp2.virtio_net.RHEL.6.1.x86_64.netperf.exhost_guest/results/netperf-result.RHS

Analysis result
===============

Config file: perf.conf

.. code-block:: cfg

  [ntttcp]
  result_file_pattern = .*.RHS
  ignore_col = 1
  avg_update =

  [netperf]
  result_file_pattern = .*.RHS
  ignore_col = 2
  avg_update = 4,2,3|14,5,12|15,6,13

  [iozone]
  result_file_pattern =

Execute regression.py to compare two results:

::

  login autotest server
  $ cd /usr/local/autotest/client/tools
  $ python regression.py netperf /usr/local/autotest/results/8-debug_user/192.168.122.1/ /usr/local/autotest/results/9-debug_user/192.168.122.1/

T-test:

* scipy: http://www.scipy.org/
* t-test: http://en.wikipedia.org/wiki/Student's_t-test
* Two python modules (scipy and numpy) are needed.
* Script to install numpy/scipy on rhel6 automatically: https://github.com/kongove/misc/blob/master/scripts/install-numpy-scipy.sh

Unpaired T-test is used to compare two samples, user can check p-value to know if regression bug exists. If the difference of two samples is considered to be not statistically significant(p <= 0.05), it will add a '+' or '-' before p-value. ('+': avg_sample1 < avg_sample2, '-': avg_sample1 > avg_sample2)

* `-` only over 95% confidence results will be added "+/-" in "Significance" part.
* `+` for cpu-usage means regression, "+" for throughput means improvement."


Regression results
==================

* Every Avg line represents the average value based on *$n* repetitions of the same test, and the following SD line represents the Standard Deviation between the *$n* repetitions.
* The Standard deviation is displayed as a percentage of the average.
* The significance of the differences between the two averages is calculated using unpaired T-test that takes into account the SD of the averages.
* The paired t-test is computed for the averages of same category.
* only over 95% confidence results will be added "+/-" in "Significance" part. "+" for cpu-usage means regression, "+" for throughput means improvement.

Highlight HTML result

* green/red --> good/bad
* Significance is larger than 0.95 --> green
* dark green/red --> important (eg: cpu)
* light green/red --> other
*  test time
* version (only when diff)
* other: repeat time, title
* user light green/red to highlight small (< %5) DIFF
* highlight Significance with same color in one raw
* add doc link to result file, and describe color in doc


`netperf.avg.html <https://github.com/kongove/misc/blob/master/html/netperf.avg.html>`_
- Raw data that the averages are based on.
