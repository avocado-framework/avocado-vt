
display
=======

Description
-----------

Sets the VM display type. Of course, only one display type is allowed,
and current valid options are: vnc, sdl, spice and nographic.

::

    display = vnc

For VNC displays, the port number is dynamically allocated within the
5900 - 6100 range.

::

    display = sdl

An SDL display does not use a port, but simply behaves as an X client.
If you want to send the SDL display to a different X Server, see
x11\_display?

::

    display = spice

For spice displays, the port number is dynamically allocated within the
8000 - 8100 range.

::

    display = nographic

nographic for qemu/kvm means that the VM will have no graphical display
and that serial I/Os will be redirected to console.

Defined On
----------

-  `shared/cfg/base.cfg <https://github.com/avocado-framework/avocado-vt/blob/master/shared/cfg/base.cfg>`_

Used By
-------

-  `virttest/qemu\_vm.py <https://github.com/avocado-framework/avocado-vt/blob/master/virttest/qemu_vm.py>`_

Referenced By
-------------

No other documentation currently references this configuration key.

