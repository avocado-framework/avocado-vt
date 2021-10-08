import logging

from six.moves import xrange

from . import env_process
from . import error_context
from . import qemu_virtio_port

LOG = logging.getLogger('avocado.' + __name__)


class VirtioPortTest(object):

    def __init__(self, test, env, params):
        self.test = test
        self.env = env
        self.params = params

    @error_context.context_aware
    def get_vm_with_ports(self, no_consoles=0, no_serialports=0, spread=None,
                          quiet=False, strict=False):
        """
        Checks whether existing 'main_vm' fits the requirements, modifies
        it if needed and returns the VM object.

        :param no_console: Number of desired virtconsoles.
        :param no_serialport: Number of desired virtserialports.
        :param spread: Spread consoles across multiple virtio-serial-pcis.
        :param quiet: Notify user about VM recreation.
        :param strict: Whether no_consoles have to match or just exceed.
        :return: vm object matching the requirements.
        """
        params = self.params.copy()
        main_vm = self.params['main_vm']
        # check the number of running VM's consoles
        vm = self.env.get_vm(main_vm)

        if not vm:
            _no_serialports = -1
            _no_consoles = -1
        else:
            _no_serialports = 0
            _no_consoles = 0
            for port in vm.virtio_ports:
                if isinstance(port, qemu_virtio_port.VirtioSerial):
                    _no_serialports += 1
                else:
                    _no_consoles += 1
        _spread = int(params.get('virtio_port_spread', 2))
        if spread is None:
            spread = _spread
        if strict:
            if (_no_serialports != no_serialports or
                    _no_consoles != no_consoles):
                _no_serialports = -1
                _no_consoles = -1
        # If not enough ports, modify params and recreate VM
        if (_no_serialports < no_serialports or
                _no_consoles < no_consoles or
                spread != _spread):
            if not quiet:
                out = "tests requirements are different from cfg: "
                if _no_serialports < no_serialports:
                    out += "serial_ports(%d), " % no_serialports
                if _no_consoles < no_consoles:
                    out += "consoles(%d), " % no_consoles
                if spread != _spread:
                    out += "spread(%s), " % spread
                LOG.warning(out[:-2] + ". Modify config to speedup tests.")

            params['serials'] = params.objects('serials')[0]
            if spread:
                params['virtio_port_spread'] = spread
            else:
                params['virtio_port_spread'] = 0

            for i in xrange(max(no_consoles, _no_consoles)):
                name = "console-%d" % i
                params['serials'] += " %s" % name
                params['serial_type_%s' % name] = "virtconsole"

            for i in xrange(max(no_serialports, _no_serialports)):
                name = "serialport-%d" % i
                params['serials'] += " %s" % name
                params['serial_type_%s' % name] = "virtserialport"

            if quiet:
                LOG.debug("Recreating VM with more virtio ports.")
            else:
                LOG.warning("Recreating VM with more virtio ports.")
            env_process.preprocess_vm(self.test, params, self.env, main_vm)
            vm = self.env.get_vm(main_vm)

        vm.verify_kernel_crash()
        return vm

    @error_context.context_aware
    def get_vm_with_worker(self, no_consoles=0, no_serialports=0, spread=None,
                           quiet=False):
        """
        Checks whether existing 'main_vm' fits the requirements, modifies
        it if needed and returns the VM object and guest_worker.

        :param no_console: Number of desired virtconsoles.
        :param no_serialport: Number of desired virtserialports.
        :param spread: Spread consoles across multiple virtio-serial-pcis.
        :param quiet: Notify user about VM recreation.
        :param strict: Whether no_consoles have to match or just exceed.
        :return: tuple (vm object matching the requirements,
                        initialized GuestWorker of the vm)
        """
        vm = self.get_vm_with_ports(no_consoles, no_serialports, spread, quiet)
        guest_worker = qemu_virtio_port.GuestWorker(vm)
        return vm, guest_worker

    @error_context.context_aware
    def get_vm_with_single_port(self, port_type='serialport'):
        """
        Wrapper which returns vm, guest_worker and virtio_ports with at lest
        one port of the type specified by function parameter.

        :param port_type: type of the desired virtio port.
        :return: tuple (vm object with at least 1 port of the port_type,
                        initialized GuestWorker of the vm,
                        list of virtio_ports of the port_type type)
        """
        if port_type == 'serialport':
            vm, guest_worker = self.get_vm_with_worker(no_serialports=1)
            virtio_ports = self.get_virtio_ports(vm)[1][0]
        else:
            vm, guest_worker = self.get_vm_with_worker(no_consoles=1)
            virtio_ports = self.get_virtio_ports(vm)[0][0]
        return vm, guest_worker, virtio_ports

    @error_context.context_aware
    def get_virtio_ports(self, vm):
        """
        Returns separated virtconsoles and virtserialports

        :param vm: VM object
        :return: tuple (all virtconsoles, all virtserialports)
        """
        consoles = []
        serialports = []
        for port in vm.virtio_ports:
            if isinstance(port, qemu_virtio_port.VirtioSerial):
                serialports.append(port)
            else:
                consoles.append(port)
        return (consoles, serialports)

    @staticmethod
    @error_context.context_aware
    def cleanup(vm=None, guest_worker=None):
        """
        Cleanup function.

        :param vm: VM whose ports should be cleaned
        :param guest_worker: guest_worker which should be cleaned/exited
        """
        error_context.context("Cleaning virtio_ports on guest.")
        if guest_worker:
            guest_worker.cleanup()
        error_context.context("Cleaning virtio_ports on host.")
        if vm:
            for port in vm.virtio_ports:
                port.clean_port()
                port.close()
                port.mark_as_clean()
