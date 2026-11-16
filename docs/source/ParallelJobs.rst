.. _parallel_jobs:

Running tests in parallel without isolation
===========================================

Avocado-VT ships with a plugin that creates a lock file in a known
public location (``/tmp`` by default, but configurable) to prevent
multiple runs of jobs that include VT tests.

The reason is that, by default, multiple jobs running at the same can
access the same data files and cause corruption.  Example of data
files are the guest images, which are usually modified, either
directly or indirectly by the tests.

Checking Installation
---------------------

The vt-joblock is installed and registered by default.  To make sure
it's active, run::

  $ avocado plugins

The VT Job lock plugin should be listed::

  Plugins that run before/after the execution of jobs (avocado.plugins.job.prepost):
  ...
  vt-joblock Avocado-VT Job Lock/Unlock
  ...

Configuration
-------------

The configuration for the vt-joblock plugin can be found at
``/etc/avocado/conf.d/vt_joblock.conf``.  Example of a configuration
file content follows::

  [plugins.vtjoblock]
  # Directory where the lock file will be located. Avocado should have permission
  # to write to this directory.
  dir=/tmp

The configuration key ``dir`` lets you set the directory where Avocado
will look for an existing lock file before running, and create one
if it doesn't exist yet.

Running Parallel Jobs
---------------------

Supposing that you have multiple users on a single machine, using
different data directories, you can allow parallel VT jobs by setting
different lock directories for each user.

To do so, you can add the customized lock directory to the user's own
Avocado configuration file.  Start by creating a lock directory::

  [user1@localhost] $ mkdir ~/avocado/data/avocado-vt/lockdir

Then modify the user's own configuration to point to the newly created
lock directory::

  [user1@localhost] $ cat >> ~/.config/avocado/avocado.conf <<EOF
  [plugins.vtjoblock]
  dir=/home/user1/avocado/data/avocado-vt/lockdir
  EOF

Then verify with::

  [user1@localhost] $ avocado config | grep plugins.vtjoblock
  ...
  plugins.vtjoblock.dir          /home/user1/avocado/data/avocado-vt/lockdir
  ...

Do the same thing for other users and their jobs will not be locked by
one another.

Running tests in parallel using LXC
===================================

Avocado itself has supported running tests in parallel for a long time, but due
to the nature of VT tests, proper parallelism requires at least an LXC container
level isolation. Assuming you have created two LXC containers c101 and c102 and
have performed the `vt-bootstrap` step in each, you can run in parallel like

    $ avocado run --spawner lxc --max-parallel-tasks 2 --vt-type qemu "only boot" "only reboot" --status-server-disable-auto --config lxc-slots.conf

Here the `--status-server-disable-auto` option can also be added in a config which
needs::

    # lxc-slots.conf
    [spawner.lxc]
    slots = ['c101', 'c102']

if e.g. there are at least two LXC containers available (slots corresponding
to the container IDs). A command line such as the above produces the output::

    JOB ID     : 07d217fbe04c17f3c045517a580f024249aeeec7
    JOB LOG    : /mnt/local/results/job-2026-08-17T22.28-07d217f/job.log
    (1/2) io-github-autotest-qemu.boot: STARTED
    (2/2) io-github-autotest-qemu.reboot: STARTED
    (1/2) io-github-autotest-qemu.boot: PASS (131.72 s)
    (2/2) io-github-autotest-qemu.reboot: PASS (326.27 s)
    RESULTS    : PASS 2 | ERROR 0 | FAIL 0 | SKIP 0 | WARN 0 | INTERRUPT 0 | CANCEL 0
    JOB HTML   : /mnt/local/results/job-2026-08-17T22.28-07d217f/results.html
    JOB TIME   : 331.12 s

The LXC containers can be easily created via the ``contrib/create_lxc_container.sh``
bash script that can be found within the code base or used as a reference.
