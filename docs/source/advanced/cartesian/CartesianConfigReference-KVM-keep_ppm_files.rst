
keep\_ppm\_files
================

Description
-----------

Configures whether should we keep the original screedump files in
`PPM <http://en.wikipedia.org/wiki/Netpbm_format>`_ format when
converting them to
`PNG <http://en.wikipedia.org/wiki/PNG_file_format>`_, according to
`convert\_ppm\_files\_to\_png <convert_ppm_files_to_png>`_

To keep the PPM files:

::

    keep_ppm_files = yes

To keep the PPM files only on situations with failures:

::

    keep_ppm_files_on_error = yes

Defined On
----------

This configuration key is not currently defined on any sample cartesian
configuration file, but a sample (commented out) appears on:

-  `client/tests/kvm/base.cfg.sample <https://github.com/autotest/autotest/blob/master/client/tests/kvm/base.cfg.sample>`_

Used By
-------

-  `client/virt/virt\_env\_process.py <https://github.com/autotest/autotest/blob/master/client/virt/virt_env_process.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

