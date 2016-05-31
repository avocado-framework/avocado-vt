.. _parallel_jobs:

Parallel Jobs
=============

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
