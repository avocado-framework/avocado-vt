"""
A module is used to interact with VMware Vshpere Server

For more examples of pyvmomi, please refer:
https://github.com/vmware/pyvmomi-community-samples
"""
import datetime
import logging

from functools import wraps

from pyVim.connect import SmartConnect, SmartConnectNoSSL, Disconnect
from pyVim.task import WaitForTask
from pyVmomi import vim

LOG = logging.getLogger('avocado.' + __name__)


def to_list(obj):
    tmp_list = []

    if not obj:
        return tmp_list

    if isinstance(obj, list):
        tmp_list.extend(obj)
    else:
        tmp_list.append(obj)
    return tmp_list


class VSphereError(Exception):
    """
    A common error for this module
    """

    def __init__(self, msg):
        self.msg = msg


class VSphereVMNotSpecified(VSphereError):
    """
    An error when the VM was not set but called vm related operation
    """

    def __init__(self, msg=None):
        if not msg:
            msg = "VM not specified"
        super(VSphereVMNotSpecified, self).__init__(msg)
        self.msg = msg

    def __str__(self):
        return self.msg


class VSphereVMNotFound(VSphereError):
    """
    An error when the VM was not found
    """

    def __init__(self, vm_name, msg=None):
        if not msg:
            msg = "VM not Found"
        super(VSphereVMNotFound, self).__init__(msg)
        self.vm = vm_name
        self.msg = msg

    def __str__(self):
        msg = '%s: %s' % (self.msg, self.vm)
        return msg


class VSphereDevNoChangeId(VSphereError):
    """
    An error when the VM was not found
    """

    def __init__(self, vm_name, dev, msg=None):
        if not msg:
            msg = "ChangeID not Found"
        super(VSphereDevNoChangeId, self).__init__(msg)
        self.vm = vm_name
        self.dev = dev
        self.msg = msg

    def __str__(self):
        msg = "%s for VM(%s): device(label='%s' key=%s)" % (
            self.msg, self.vm, self.dev.deviceInfo.label, self.dev.key)
        return msg


class VSphereSnapNotFound(VSphereError):
    """
    An error when the snapshot of the VM was not found
    """

    def __init__(self, vm_name, snapshot_id, msg=None):
        if not msg:
            msg = "snapshot not Found"
        super(VSphereSnapNotFound, self).__init__(msg)
        self.vm = vm_name
        self.snapshot_id = snapshot_id
        self.msg = msg

    def __str__(self):
        msg = '%s for VM %s: %s' % (self.msg, self.vm, self.snapshot_id)
        return msg


class VSphereInvalidDevType(VSphereError):
    """
    An error when the snapshot of the VM was not found
    """

    def __init__(self, dev_type, msg=None):
        if not msg:
            msg = "Invalid device Type"
        super(VSphereInvalidDevType, self).__init__(msg)
        self.dev_type = dev_type
        self.msg = msg

    def __str__(self):
        msg = '%s: %s' % (self.msg, self.dev_type)
        return msg


class VSphereConnection(object):
    """
    This is a useful class when you want to do some temporary
    operation. The class can do initialization and cleanup
    automatically.
    Besides the necessary parameters of VSphere, you can pass
    a 'vm_name' parameter to set the target_vm automatically.

    Examples:
    >>> from utils_pyvmomi import *
    >>> connect_args = {'host': "x.x.x.x", 'user': 'root', 'pwd': 'xxx', 'vm_name': 'pyvmomi-rhel8.1'}
    >>> with VSphereConnection(**connect_args) as conn:
        ...     print(conn.get_vm_summary()['mac_address'])
        ...
        ['00:50:56:ac:09:3e']

    or set the target_vm later.

    >>> connect_args = {'host': "x.x.x.x", 'user': 'root', 'pwd': 'xxx'}
    >>> with VSphereConnection(**connect_args) as conn:
    ...     conn.target_vm = 'pyvmomi-rhel8.1'
    ...     print(conn.get_vm_summary()['mac_address'])
    ...
    ['00:50:56:ac:09:3e']

    """

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.vsphere_conn = None

        try:
            self.vm_name = self.kwargs.pop('vm_name')
        except KeyError:
            self.vm_name = None

    def __enter__(self):
        self.vsphere_conn = VSphere(*self.args, **self.kwargs)
        self.vsphere_conn.connect()
        if self.vm_name:
            self.vsphere_conn.target_vm = self.vm_name
        return self.vsphere_conn

    def __exit__(self, *exc_info):
        self.vsphere_conn.close()


class VSphere(object):
    """
    The VShpere class is used to do interactive with vshpere server.

    It's a convenient class for testing, Users don't have to spend much
    time on pyVmomi.

    By this class, you can query basic information of a VM, do power
    on/off, create snapshot, etc.

    More functions will be added if it's necessary for testing.

    Examples:

    >>> connect_args = {'host': "x.x.x.x", 'user': 'root', 'pwd': 'xxx'}
    >>> conn = VSphere(**connect_args)
    >>> conn.target_vm = 'pyvmomi-rhel8.1'
    >>> print(conn.get_vm_summary()['mac_address'])
    ['00:50:56:ac:09:3e']
    >>> conn.close()
    """

    def __init__(self, insecure=True, **kwargs):
        """
        An initialization function for VShpere Class

        For the full supported parameters, please refer:
        https://github.com/vmware/pyvmomi/blob/master/pyVim/connect.py

        Some basic parameter are:

        :param host: ip or hostname of vshpere server
        :param port: a port number, default is 443
        :param user: user name, default is 'root'
        :param pwd: password
        :param insecure: If true, the connection will have no SSL.
                         Default is True.
        """
        self.insecure = insecure
        self.kwargs = kwargs

        # An service instance to VSphere server
        self.service_instance = None

        # An internal vm object.
        # Users should use 'target_vm' instead of this one.
        self._target_vm = None
        # Use to recover the conn when it's dead
        self._target_vm_name = None

    def connect(self):
        """
        Initialize the service instance to the VSphere server
        """
        # Check if an valid connection has already been established.
        # If yes, just refresh the connection to keep it alive.
        # If not, close the old connection and establishes a new one.
        if self.is_conn_dead():
            self.close()
        else:
            self.keep_alive()
            return

        kwargs = self.kwargs

        if self.insecure:
            self.service_instance = SmartConnectNoSSL(**kwargs)
        else:
            self.service_instance = SmartConnect(**kwargs)

        if self.service_instance:
            LOG.debug(
                'New vsphere connection established: %s (%s)',
                self.service_instance, id(self.service_instance))

    def close(self):
        """
        Cleanup the vsphere resources
        """
        del self.target_vm
        if not self.service_instance:
            return
        LOG.debug('vsphere connection closed: %s (%s)',
                  self.service_instance, id(self.service_instance))
        Disconnect(self.service_instance)
        self.service_instance = None

    def keep_alive(self):
        """
        Get the time of vshpere server to keep the connection alive
        """
        self.service_instance.serverClock

    def is_conn_dead(self):
        """
        Check if the connection is dead.

        If it's dead, return True, else
        return False.
        """
        if not self.service_instance:
            return True
        try:
            self.keep_alive()
        except vim.fault.NotAuthenticated:
            return True
        return False

    # pylint: disable=E0213
    def vm_picker(f):
        """
        A decorator function is used to determine if which VM object
        should be used.

        Users can specify an vshpere vm object to 'vm_obj', or a vm
        name to 'vm_name'. This function can help to find the vm by its
        name.

        If both 'vm_obj' and 'vm_name' are passed, 'vm' will be used instead
        of 'vm_name'.

        Note: If target_vm was set, then you do get_mac_address(vm_name='another-vm'),
        It will not work as expected. Because the target_vm will be used
        instead of new vm specified by 'vm_name'. You need to change
        target_vm by 'self.target_vm = new_vm_name'

        Examples:

        >>> conn.target_vm.name
        'pyvmomi-rhel8.1'
        >>> conn.get_mac_address(vm_obj=conn.target_vm)
        ['00:50:56:ac:09:3e']
        >>> conn.get_mac_address(vm_name='esx6.5-rhel6.9-i386')
        ['00:50:56:ac:09:3e']
        >>> conn.target_vm = 'esx6.5-rhel6.9-i386'
        >>> conn.get_mac_address(vm_name='esx6.5-rhel6.9-i386')
        ['00:50:56:a2:ee:5e']

        """
        @wraps(f)
        def wraper(self, *args, **kwargs):
            vmobj = kwargs.get('vm_obj')
            vm_name = kwargs.get('vm_name')
            if not vmobj:
                if self.target_vm:
                    # If conn is dead, reassign the
                    # vm to active a new conn.
                    if self.is_conn_dead():
                        self.target_vm = self._target_vm_name
                    vmobj = self.target_vm
                    if vm_name:
                        LOG.warning(
                            "Have you forgotten to reset target_vm to 'new vm name'?")
                elif vm_name:
                    self.target_vm = vm_name
                    vmobj = self.target_vm
                else:
                    raise VSphereVMNotSpecified

                kwargs.update({'vm_obj': vmobj})

            # pylint: disable=E1102
            return f(self, *args, **kwargs)
        return wraper

    def get_all_vms(self):
        """
        Return all VMs on VSphere
        """
        self.connect()
        content = self.service_instance.RetrieveContent()
        container_view = content.viewManager.CreateContainerView(
            self.service_instance.RetrieveContent().rootFolder, [vim.VirtualMachine], True)
        return [vm for vm in container_view.view]

    def _get_vm(self):
        """
        Get VM
        """
        return self._target_vm

    def _set_vm(self, name):
        """
        Set VM by name

        :param name: a vm's name
        """
        # For vm recovery if failed
        tmp_vm = self._target_vm
        # Clean up old VM
        self._target_vm = None
        # Connect to VSphere server
        self.connect()
        # Could two VM names be same on VSphere?
        # Right now the code only returns the first found VM
        for vm in self.get_all_vms():
            if vm.name == name:
                self._target_vm = vm
                break
        # Not Found
        if not self._target_vm:
            # Restore the target_vm to old value
            self._target_vm = tmp_vm
            raise VSphereVMNotFound(name)
        self._target_vm_name = self._target_vm.name
        LOG.debug('Current target VM is %s' % self._target_vm.name)

    def _del_vm(self):
        """
        Clean up the vm but not delete it
        """
        self._target_vm = None

    # This property stands a target vm object in vsphere.
    # e.g. vim.VirtualMachine:vm-1464
    target_vm = property(
        _get_vm,
        _set_vm,
        _del_vm,
        "The target VM to check and update.")

    @vm_picker
    def get_mac_address(self, vm_obj=None, vm_name=None):
        """
        Return all mac addresses of the VM

        :param vm_obj: a vsphere vm object
        :param vm_name: a vm's name
        """
        mac_list = []
        for dev in vm_obj.config.hardware.device:
            if isinstance(dev, vim.vm.device.VirtualEthernetCard):
                mac_list.append(dev.macAddress)
        return mac_list

    @vm_picker
    def get_vm_summary(self, vm_obj=None, vm_name=None):
        """
        Return some configurations of the VM

        Note: For 'ip_address', It takes some time for the guest
        to obtain the value. You need to keep trying it.

        :param vm_obj: a vsphere vm object
        :param vm_name: a vm's name
        """
        vm_summary = {}
        raw_vmsummary = vm_obj.summary

        # vim.vm.Summary.ConfigSummary
        vm_summary['name'] = raw_vmsummary.config.name
        vm_summary['memory_mb'] = raw_vmsummary.config.memorySizeMB
        vm_summary['vm_path'] = raw_vmsummary.config.vmPathName
        vm_summary['num_cpu'] = raw_vmsummary.config.numCpu
        vm_summary['num_cores_per_socket'] = vm_obj.config.hardware.numCoresPerSocket
        vm_summary['num_ethernet_cards'] = raw_vmsummary.config.numEthernetCards
        vm_summary['num_virtual_disks'] = raw_vmsummary.config.numVirtualDisks
        vm_summary['uuid'] = raw_vmsummary.config.uuid
        vm_summary['instance_uuid'] = raw_vmsummary.config.instanceUuid

        # vim.vm.summary.runtime
        vm_summary['power_state'] = raw_vmsummary.runtime.powerState

        # vim.vm.summary.guest
        vm_summary['hostname'] = raw_vmsummary.guest.hostName
        vm_summary['ip_address'] = raw_vmsummary.guest.ipAddress
        vm_summary['mac_address'] = self.get_mac_address(
            vm_obj=vm_obj, vm_name=vm_name)

        return vm_summary

    @vm_picker
    def power_on(self, vm_obj=None, vm_name=None):
        """
        Power on the VM

        :param vm_obj: a vsphere vm object
        :param vm_name: a vm's name
        """
        WaitForTask(vm_obj.PowerOn())
        LOG.debug('VM %s was powered on', vm_obj.name)

    @vm_picker
    def power_off(self, vm_obj=None, vm_name=None):
        """
        Force power off the VM

        This may cause windows guests to enter emergency
        recovery mode.

        :param vm_obj: a vsphere vm object
        :param vm_name: a vm's name
        """
        WaitForTask(vm_obj.PowerOff())
        LOG.debug('VM %s was powered off', vm_obj.name)

    @vm_picker
    def remove_all_snapshots(self, vm_obj=None, vm_name=None):
        """
        Remove all snapshots of the VM

        :param vm_obj: a vsphere vm object
        :param vm_name: a vm's name
        """
        if not vm_obj.snapshot:
            return
        LOG.debug('Remove all snapshots for VM %s', vm_obj.name)
        WaitForTask(vm_obj.RemoveAllSnapshots())

    @vm_picker
    def remove_current_snapshot(self, vm_obj=None, vm_name=None):
        """
        Remove current snapshot of the VM

        :param vm_obj: a vsphere vm object
        :param vm_name: a vm's name
        """
        if not vm_obj.snapshot:
            return
        LOG.debug('Remove current snapshot for VM %s', vm_obj.name)
        WaitForTask(
            vm_obj.snapshot.currentSnapshot.Remove(
                removeChildren=True))

    @vm_picker
    def find_snapshot_by_id(self, snapshot_id, vm_obj=None, vm_name=None):
        """
        Find a vm's snapshot by the snapshot ID

        The snapshot ID should be saved when creating a snapshot if you
        need to use it in this function.

        A snapshot obj in pyvmomi is like 'vim.vm.Snapshot:snapshot-1474',
        the snapshot ID is 'snapshot-1474'

        :param snapshot_id: a snapshot ID
        :param vm_obj: a vsphere vm object
        :param vm_name: a vm's name
        """
        def _find_snapshot_by_recursive(snap, snapshot_id):
            if snapshot_id == snap.snapshot._moId:
                return snap.snapshot
            for child_snap in snap.childSnapshotList:
                return _find_snapshot_by_recursive(child_snap, snapshot_id)
            return None

        if not vm_obj.snapshot:
            return None

        for snap_tree in vm_obj.snapshot.rootSnapshotList:
            return _find_snapshot_by_recursive(snap_tree, snapshot_id)
        # This return should not be executed in theory.
        return None

    @vm_picker
    def remove_snapshot_by_id(
            self,
            snapshot_id,
            vm_obj=None,
            vm_name=None,
            remove_children=True,
            raise_not_found=False):
        """
        Remove a vm's snapshot by the snapshot ID

        The snapshot ID should be saved when creating a snapshot if you
        need to use it in this function.

        A snapshot obj in pyvmomi is like 'vim.vm.Snapshot:snapshot-1474',
        the snapshot ID is 'snapshot-1474'

        :param snapshot_id: a snapshot ID
        :param vm_obj: a vsphere vm object
        :param vm_name: a vm's name
        :param remove_children: whether to remove snapshot's children snapshots
        :param raise_not_found: whether to raise exception if snapshot_id not found
        """
        snap = self.find_snapshot_by_id(snapshot_id)
        if not snap:
            if raise_not_found:
                raise VSphereSnapNotFound(vm_obj.name, snapshot_id)
            else:
                LOG.debug(
                    'Not found snapshot_id %s for VM %s',
                    snapshot_id,
                    vm_obj.name)
                return

        LOG.debug('Remove snapshot %s for VM %s', snap, vm_obj.name)
        WaitForTask(snap.Remove(removeChildren=remove_children))

    @vm_picker
    def create_snapshot(self, vm_obj=None, vm_name=None):
        """
        Create a snapshot for the VM

        The snapshot ID should be saved when creating a snapshot in order
        to use it later.

        :param vm_obj: a vsphere vm object
        :param vm_name: a vm's name
        """
        # Enable CBT for change tracking
        config_spec = vim.vm.ConfigSpec(changeTrackingEnabled=True)
        WaitForTask(vm_obj.Reconfigure(config_spec))
        WaitForTask(
            vm_obj.CreateSnapshot(
                name='Testing Snapshot CBT',
                description='Created at %s by Avocado-VT on testing host' %
                str(
                    datetime.datetime.now()),
                memory=False,
                quiesce=True))

    @vm_picker
    def get_hardware_devices(
            self,
            vm_obj=None,
            vm_name=None,
            devices=None,
            dev_type=None):
        """
        Return all hardware devices of the VM or filter the devices
        by dev_type.

        If not specified a device type, all devices will be returned.
        If some devices are passed, this function can filter those devices by dev_type.

        Possible values for 'dev_type' are as below:
            vim.vm.device.VirtualCdrom, vim.vm.device.VirtualController,
            vim.vm.device.VirtualDisk, vim.vm.device.VirtualEthernetCard,
            vim.vm.device.VirtualFloppy, vim.vm.device.VirtualKeyboard,
            vim.vm.device.VirtualMachineVideoCard, vim.vm.device.VirtualMachineVMCIDevice,
            vim.vm.device.VirtualMachineVMIROM, vim.vm.device.VirtualNVDIMM,
            vim.vm.device.VirtualParallelPort, vim.vm.device.VirtualPCIPassthrough,
            vim.vm.device.VirtualPointingDevice, vim.vm.device.VirtualSCSIPassthrough,
            vim.vm.device.VirtualSerialPort, vim.vm.device.VirtualSoundCard,
            vim.vm.device.VirtualTPM, vim.vm.device.VirtualUSB

        :param vm_obj: a vsphere vm object
        :param vm_name: a vm's name
        :param devices: a device object return by pyvmomi
        :param dev_type: the type of the device.
        """
        vm_devs = devices if devices else vm_obj.config.hardware.device

        if not dev_type:
            return vm_devs

        if dev_type and issubclass(dev_type, vim.vm.device.VirtualDevice):
            devs = []
            for dev in vm_devs:
                if isinstance(dev, dev_type):
                    devs.append(dev)
            return devs
        else:
            raise VSphereInvalidDevType(dev_type)

    def get_dev_by_key_or_label(self, devices, label=None, key=None):
        """
        Get devices by key or label.

        Return device with label matched or key matched.
        If both label and key are specified, the device matches both
        of them is returned.

        :param devices: a device object return by pyvmomi
        :param label: a device's label
        :param key: A unique value to identify a device
        """

        devs = to_list(devices)

        conds = []
        if label:
            conds.append(lambda dev: dev.deviceInfo.label == label)
        if key:
            conds.append(lambda dev: dev.key == key)
        if not conds:
            raise VSphereError("At least a label or a key must be specified")

        res = [dev for dev in devs if all([cond(dev) for cond in conds])]
        if len(res) > 1:
            raise VSphereError(
                "Mutiple devices are found for label(%s) or key(%s)" %
                (label, key))

        if not res:
            raise VSphereError(
                "Not found device for label(%s) or key(%s)" %
                (label, key))

        LOG.debug(
            "Found device: label(%s) key(%s) summary(%s)",
            res[0].deviceInfo.label,
            res[0].key,
            res[0].deviceInfo.summary)
        return res[0]

    @vm_picker
    def query_changed_disk_areas(
            self,
            vm_obj=None,
            vm_name=None,
            start_offset=0,
            disk_label=None,
            disk_key=None,
            snapshot=None,
            snapshot_id=None):
        """
        Get a list of areas of a virtual disk belonging to this VM that
        have been modified since a well-defined point in the past.
        The beginning of the change interval is identified by "changeId",
        while the end of the change interval is implied by the snapshot ID
        passed in.

        :param vm_obj: a vsphere vm object
        :param vm_name: a vm's name
        :param disk_label: a device's label
        :param disk_key: A unique value to identify a device
        :param start_offset: Start Offset in bytes at which to start
            computing changes. Typically, callers will make multiple
            calls to this function, starting with startOffset 0 and
            then examine the "length" property in the returned
            DiskChangeInfo structure, repeatedly calling queryChangedDiskAreas
            until a map forthe entire virtual disk has been obtained.
        :param snapshot: Snapshot for which changes that have been made
            sine "changeId" should be computed. If not set, changes are
            computed against the "current" snapshot of the virtual machine.
            However, using the "current" snapshot will only work for
            virtual machines that are powered off.
        :param snapshot_id: a snapshot ID
        """
        # If not set snapshot but snapshot_id, find it by
        # snapshot id.
        if not snapshot and snapshot_id:
            snapshot = self.find_snapshot_by_id(snapshot_id)

        if not snapshot:
            all_devs = vm_obj.snapshot.currentSnapshot.config.hardware.device
        else:
            all_devs = snapshot.config.hardware.device

        disk_devs = self.get_hardware_devices(
            devices=all_devs, dev_type=vim.vm.device.VirtualDisk)
        dev = self.get_dev_by_key_or_label(disk_devs, disk_label, disk_key)
        if not dev.backing.changeId:
            raise VSphereDevNoChangeId(vm_obj.name, dev)

        # if snapshot is None, currentsnapshot is used
        return vm_obj.QueryChangedDiskAreas(
            snapshot, dev.key, start_offset, dev.backing.changeId)
