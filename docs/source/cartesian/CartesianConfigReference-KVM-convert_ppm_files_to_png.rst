
convert\_ppm\_files\_to\_png
============================

Description
-----------

Configures whether files generated from screenshots in `PPM
format <http://en.wikipedia.org/wiki/Netpbm_format>`_ should be
automatically converted to
`PNG <http://en.wikipedia.org/wiki/PNG_file_format>`_ files.

::

    convert_ppm_files_to_png = yes

Usually we're only interested in spending time converting files for
easier viewing on situations with failures:

::

    convert_ppm_files_to_png_on_error = yes

Defined On
----------

The stock configuration key (without suffix) is not currently defined on
any sample cartesian configuration file.

The configuration key with the 'on\_error' suffix is defined on:

-  `shared/cfg/base.cfg <https://github.com/avocado-framework/avocado-vt/blob/master/shared/cfg/base.cfg>`_

Used By
-------

-  `virttest/env\_process.py <https://github.com/avocado-framework/avocado-vt/blob/master/virttest/env_process.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

