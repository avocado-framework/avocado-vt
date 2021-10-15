"""
oVirt SDK wrapper module.

:copyright: 2008-2012 Red Hat Inc.
"""


import time
import logging

import ovirtsdk4 as sdk
import ovirtsdk4.types as types

from virttest import virt_vm
from virttest.utils_net import ping


_api = None
_connected = False

LOG = logging.getLogger('avocado.' + __name__)


class WaitStateTimeoutError(Exception):

    def __init__(self, msg, output):
        Exception.__init__(self, msg, output)
        self.msg = msg
        self.output = output


class WaitVMStateTimeoutError(WaitStateTimeoutError):

    def __str__(self):
        str = "Timeout expired when waiting for VM to %s,"
        str += " actual state is: %s"
        return str % (self.msg, self.output)


class WaitHostStateTimeoutError(WaitStateTimeoutError):

    def __str__(self):
        str = "Timeout expired when waiting for Host to %s,"
        str += " actual state is: %s"
        return str % (self.msg, self.output)


def connect(params):
    """
    Connect ovirt manager API.
    """
    url = params.get('ovirt_engine_url')
    username = params.get('ovirt_engine_user')
    password = params.get('ovirt_engine_password')

    if not all([url, username, password]):
        LOG.error('ovirt_engine[url|user|password] are necessary!!')

    global connection, _connected, version

    try:
        # Try to connect oVirt API if connection doesn't exist,
        # otherwise, directly return existing API connection.
        if not _connected:
            connection = sdk.Connection(
                url=url,
                username=username,
                password=password,
                insecure=True
            )
            version = connection.system_service().get().product_info.version
            _connected = True
            return connection, version
        else:
            return connection, version
    except Exception as e:
        LOG.error('Failed to connect: %s\n' % str(e))
    else:
        LOG.info('Succeed to connect oVirt/Rhevm manager\n')


def disconnect():
    """
    Disconnect ovirt manager connection.
    """
    global connection, _connected

    if _connected:
        return connection.close()


class VMManager(virt_vm.BaseVM):

    """
    This class handles all basic VM operations for oVirt.
    """

    def __init__(self, name, params, root_dir=None, address_cache=None,
                 state=None):
        """
        Initialize the object and set a few attributes.

        :param name: The name of the object
        :param params: A dict containing VM params (see method
                       make_create_command for a full description)
        :param root_dir: Base directory for relative filenames
        :param address_cache: A dict that maps MAC addresses to IP addresses
        :param state: If provided, use this as self.__dict__
        """

        if state:
            self.__dict__ = state
        else:
            self.process = None
            self.serial_console = None
            self.redirs = {}
            self.vnc_port = 5900
            self.vnclisten = "0.0.0.0"
            self.pci_assignable = None
            self.netdev_id = []
            self.device_id = []
            self.pci_devices = []
            self.uuid = None
            self.only_pty = False
            self.remote_sessions = []

        self.spice_port = 8000
        self.name = name
        self.params = params
        self.root_dir = root_dir
        self.address_cache = address_cache
        self.vnclisten = "0.0.0.0"
        self.driver_type = "v2v"

        super(VMManager, self).__init__(self.name, params)
        (self.connection, self.version) = connect(params)

        if self.name:
            self.update_instance()

    def update_instance(self):
        vms_service = self.connection.system_service().vms_service()
        vms = vms_service.list(search='name=%s' % self.name)
        if vms:
            vm = vms[0]
            self.instance = vms_service.vm_service(vm.id)
        else:
            self.instance = None

    def list(self):
        """
        List all of VMs.
        """
        vm_list = []
        try:
            vms = self.connection.system_service().vms_service().list()
            for i in range(len(vms)):
                vm_list.append(vms[i].name)
            return vm_list
        except Exception as e:
            LOG.error('Failed to get vms:\n%s' % str(e))

    def state(self):
        """
        Return VM state.
        """
        try:
            self.update_instance()
            return self.instance.get().status
        except Exception as e:
            LOG.error('Failed to get %s status:\n%s' % (self.name, str(e)))

    def get_mac_address(self, net_name='*'):
        """
        Return MAC address of a VM.
        """
        if not self.instance:
            self.update_instance()
        vnet_list = self.instance.nics_service().list()
        if net_name != '*':
            vnet_list = [vnet for vnet in vnet_list if vnet.name == net_name]
        try:
            return [vnet.mac.address for vnet in vnet_list if vnet.mac.address]
        except Exception as e:
            LOG.error('Failed to get %s status:\n%s' % (self.name, str(e)))

    def lookup_by_storagedomains(self, storage_name):
        """
        Lookup VM object in storage domain according to VM name.
        """
        try:
            sds_service = self.connection.system_service().storage_domains_service()
            export_sd = sds_service.list(search=storage_name)[0]
            export_vms_service = sds_service.storage_domain_service(export_sd.id).vms_service()
            target_vm = [vm for vm in export_vms_service.list() if vm.name == self.name][0]
            return target_vm
        except Exception as e:
            LOG.error('Failed to get %s from %s:\n%s' % (self.name,
                                                         storage_name, str(e)))

    def is_dead(self):
        """
        Judge if a VM is dead.
        """
        if self.state() == types.VmStatus.DOWN:
            LOG.info('VM %s status is <Down>' % self.name)
            return True
        else:
            return False

    def is_alive(self):
        """
        Judge if a VM is alive.
        """
        return not self.is_dead()

    def is_paused(self):
        """
        Return if VM is suspend.
        """
        if self.state() == types.VmStatus.SUSPENDED:
            return True
        else:
            LOG.debug('VM %s status is %s ' % (self.name, self.state()))
            return False

    def start(self, wait_for_up=True, timeout=300):
        """
        Start a VM.
        """
        end_time = time.time() + timeout
        if self.is_dead():
            LOG.info('Starting VM %s' % self.name)
            self.instance.start()
            vm_powering_up = False
            vm_up = False
            while time.time() < end_time:
                if self.state() == types.VmStatus.POWERING_UP:
                    vm_powering_up = True
                    if wait_for_up:
                        LOG.info('Waiting for VM to reach <Up> status')
                        if self.state() == types.VmStatus.UP:
                            vm_up = True
                            break
                    else:
                        break
                elif self.state() == types.VmStatus.UP:
                    vm_up = True
                    break
                time.sleep(1)
            if not vm_powering_up and not vm_up:
                raise WaitVMStateTimeoutError("START", self.state())
        else:
            LOG.debug('VM is alive')

    def suspend(self, timeout):
        """
        Suspend a VM.
        """
        end_time = time.time() + timeout
        vm_suspend = False
        while time.time() < end_time:
            try:
                LOG.info('Suspend VM %s' % self.name)
                self.instance.suspend()
                LOG.info('Waiting for VM to reach <Suspended> status')
                if self.is_paused():
                    vm_suspend = True
                    break
            except Exception as e:
                if e.reason == 'Bad Request' \
                        and 'asynchronous running tasks' in e.detail:
                    LOG.warning("VM has asynchronous running tasks, "
                                "trying again")
                    time.sleep(1)
                else:
                    raise e
            time.sleep(1)
        if not vm_suspend:
            raise WaitVMStateTimeoutError("SUSPEND", self.state())

    def resume(self, timeout):
        """
        Resume a suspended VM.
        """
        end_time = time.time() + timeout
        try:
            if self.state() != 'up':
                LOG.info('Resume VM %s' % self.name)
                self.instance.start()
                LOG.info('Waiting for VM to <UP> status')
                vm_resume = False
                while time.time() < end_time:
                    if self.state() == types.VmStatus.UP:
                        vm_resume = True
                        break
                    time.sleep(1)
                if not vm_resume:
                    raise WaitVMStateTimeoutError("RESUME", self.state())
            else:
                LOG.debug('VM already up')
        except Exception as e:
            LOG.error('Failed to resume VM:\n%s' % str(e))

    def shutdown(self, gracefully=True, timeout=300):
        """
        Shut down a running VM.
        """
        end_time = time.time() + timeout
        if self.is_alive():
            LOG.info('Shutdown VM %s' % self.name)
            if gracefully:
                self.instance.shutdown()
            else:
                self.instance.stop()
            LOG.info('Waiting for VM to reach <Down> status')
            vm_down = False
            while time.time() < end_time:
                if self.is_dead():
                    vm_down = True
                    break
                time.sleep(1)
            if not vm_down:
                raise WaitVMStateTimeoutError("DOWN", self.state())
        else:
            LOG.debug('VM already down')

    def delete(self, timeout=300):
        """
        Delete a VM.
        """
        end_time = time.time() + timeout
        if self.name in self.list():
            LOG.info('Delete VM %s' % self.name)
            self.instance.remove()
            LOG.info('Waiting for VM to be <Deleted>')
            vm_delete = False
            while time.time() < end_time:
                if self.name not in self.list():
                    vm_delete = True
                    break
                time.sleep(1)
            if not vm_delete:
                raise WaitVMStateTimeoutError("DELETE", self.state())
            LOG.info('VM was removed successfully')
        else:
            LOG.debug('VM not exist')

    def destroy(self, gracefully=False):
        """
        Destroy a VM.
        """
        if not self.connection.system_service().vms_service().list():
            return
        self.shutdown(gracefully)

    def delete_from_export_domain(self, export_name):
        """
        Remove a VM from specified export domain.

        :param export_name: export domain name.
        """
        vm = self.lookup_by_storagedomains(export_name)
        try:
            sds_service = self.connection.system_service().storage_domains_service()
            export_sd = sds_service.list(search=export_name)[0]
            LOG.info('Remove VM %s from export storage' % self.name)
            export_vms_service = sds_service.storage_domain_service(export_sd.id).vms_service()
            export_vms_service.vm_service(vm.id).remove()
        except Exception as e:
            LOG.error('Failed to remove VM:\n%s' % str(e))

    def import_from_export_domain(self, export_name, storage_name,
                                  cluster_name, timeout=300):
        """
        Import a VM from export domain to data domain.

        :param export_name: Export domain name.
        :param storage_name: Storage domain name.
        :param cluster_name: Cluster name.
        :param timeout: timeout value
        """
        begin_time = time.time()
        end_time = time.time() + timeout
        vm = self.lookup_by_storagedomains(export_name)
        sds_service = self.connection.system_service().storage_domains_service()
        export_sd = sds_service.list(search=export_name)[0]
        storage_domains = sds_service.list(search=storage_name)[0]
        clusters_service = self.connection.system_service().clusters_service()
        cluster = clusters_service.list(search=cluster_name)[0]
        LOG.info('Import VM %s' % self.name)
        export_vms_service = sds_service.storage_domain_service(export_sd.id).vms_service()
        export_vms_service.vm_service(vm.id).import_(
            storage_domain=types.StorageDomain(id=storage_domains.id),
            cluster=types.Cluster(id=cluster.id),
            vm=types.Vm(id=vm.id),
            exclusive=False
        )
        LOG.info('Waiting for VM to reach <Down> status')
        vm_down = False
        while time.time() < end_time:
            if self.name in self.list():
                if self.is_dead():
                    vm_down = True
                    break
            time.sleep(1)
        if not vm_down:
            raise WaitVMStateTimeoutError("DOWN", self.state())
        LOG.info('Import %s successfully(time lapse %ds)',
                 self.name, time.time() - begin_time)

    def export_from_export_domain(self, export_name, timeout=300):
        """
        Export a VM from storage domain to export domain.

        :param export_name: Export domain name.
        """
        end_time = time.time() + timeout
        storage_domains = self.connection.storagedomains.get(export_name)
        LOG.info('Export VM %s' % self.name)
        self.instance.export(types.Action(storage_domain=storage_domains))
        LOG.info('Waiting for VM to reach <Down> status')
        vm_down = False
        while time.time() < end_time:
            if self.is_dead():
                vm_down = True
                break
            time.sleep(1)
        if not vm_down:
            raise WaitVMStateTimeoutError("DOWN", self.state())
        LOG.info('Export %s successfully', self.name)

    def snapshot(self, snapshot_name='my_snapshot', timeout=300):
        """
        Create a snapshot to VM.

        :param snapshot_name: 'my_snapshot' is default snapshot name.
        :param timeout: Time out
        """
        end_time = time.time() + timeout
        snap_params = types.Snapshot(description=snapshot_name,
                                     vm=self.instance)
        LOG.info('Creating a snapshot %s for VM %s'
                 % (snapshot_name, self.name))
        self.instance.snapshots.add(snap_params)
        LOG.info('Waiting for snapshot creation to finish')
        vm_snapsnop = False
        while time.time() < end_time:
            if self.state() != 'image_locked':
                vm_snapsnop = True
                break
            time.sleep(1)
        if not vm_snapsnop:
            raise WaitVMStateTimeoutError("SNAPSHOT", self.state())
        LOG.info('Snapshot was created successfully')

    def create_template(self, cluster_name, template_name='my_template', timeout=300):
        """
        Create a template from VM.

        :param cluster_name: cluster name.
        :param template_name: 'my_template' is default template name.
        :param timeout: Time out
        """
        end_time = time.time() + timeout
        cluster = self.connection.clusters.get(cluster_name)

        tmpl_params = types.Template(name=template_name,
                                     vm=self.instance,
                                     cluster=cluster)
        try:
            LOG.info('Creating a template %s from VM %s'
                     % (template_name, self.name))
            self.connection.templates.add(tmpl_params)
            LOG.info('Waiting for VM to reach <Down> status')
            vm_down = False
            while time.time() < end_time:
                if self.is_dead():
                    vm_down = True
                    break
                time.sleep(1)
            if not vm_down:
                raise WaitVMStateTimeoutError("DOWN", self.state())
        except Exception as e:
            LOG.error('Failed to create a template from VM:\n%s' % str(e))

    def add(self, memory, disk_size, cluster_name, storage_name,
            nic_name='eth0', network_interface='virtio',
            network_name='ovirtmgmt', disk_interface='virtio',
            disk_format='raw', template_name='Blank', timeout=300):
        """
        Create VM with one NIC and one Disk.

        :param memory: VM's memory size such as 1024*1024*1024=1GB.
        :param disk_size: VM's disk size such as 512*1024=512MB.
        :param nic_name: VM's NICs name such as 'eth0'.
        :param network_interface: VM's network interface such as 'virtio'.
        :param network_name: network such as ovirtmgmt for ovirt, rhevm for rhel.
        :param disk_format: VM's disk format such as 'raw' or 'cow'.
        :param disk_interface: VM's disk interface such as 'virtio'.
        :param cluster_name: cluster name.
        :param storage_name: storage domain name.
        :param template_name: VM's template name, default is 'Blank'.
        :param timeout: Time out
        """
        end_time = time.time() + timeout
        # network name is ovirtmgmt for ovirt, rhevm for rhel.
        vm_params = types.VM(name=self.name, memory=memory,
                             cluster=self.connection.clusters.get(cluster_name),
                             template=self.connection.templates.get(template_name))

        storage = self.connection.storagedomains.get(storage_name)

        storage_params = types.StorageDomains(storage_domain=[storage])

        nic_params = types.NIC(name=nic_name,
                               network=types.Network(name=network_name),
                               interface=network_interface)

        disk_params = types.Disk(storage_domains=storage_params,
                                 size=disk_size,
                                 type_='system',
                                 status=None,
                                 interface=disk_interface,
                                 format=disk_format,
                                 sparse=True,
                                 bootable=True)

        try:
            LOG.info('Creating a VM %s' % self.name)
            self.connection.vms.add(vm_params)

            LOG.info('NIC is added to VM %s' % self.name)
            self.instance.nics.add(nic_params)

            LOG.info('Disk is added to VM %s' % self.name)
            self.instance.disks.add(disk_params)

            LOG.info('Waiting for VM to reach <Down> status')
            vm_down = False
            while time.time() < end_time:
                if self.is_dead():
                    vm_down = True
                    break
                time.sleep(1)
            if not vm_down:
                raise WaitVMStateTimeoutError("DOWN", self.state())
        except Exception as e:
            LOG.error('Failed to create VM with disk and NIC\n%s' % str(e))

    def add_vm_from_template(self, cluster_name, template_name='Blank',
                             new_name='my_new_vm', timeout=300):
        """
        Create a VM from template.

        :param cluster_name: cluster name.
        :param template_name: default template is 'Blank'.
        :param new_name: 'my_new_vm' is a default new VM's name.
        :param timeout: Time out
        """
        end_time = time.time() + timeout
        vm_params = types.VM(name=new_name,
                             cluster=self.connection.clusters.get(cluster_name),
                             template=self.connection.templates.get(template_name))
        try:
            LOG.info('Creating a VM %s from template %s'
                     % (new_name, template_name))
            self.connection.vms.add(vm_params)
            LOG.info('Waiting for VM to reach <Down> status')
            vm_down = False
            while time.time() < end_time:
                if self.is_dead():
                    vm_down = True
                    break
                time.sleep(1)
            if not vm_down:
                raise WaitVMStateTimeoutError("DOWN", self.state())
            LOG.info('VM was created from template successfully')
        except Exception as e:
            LOG.error('Failed to create VM from template:\n%s' % str(e))

    def get_address(self, index=0, *args):
        """
        Return the address of the guest through ovirt node tcpdump cache.

        :param index: Name or index of the NIC whose address is requested.
        :return: IP address of NIC.
        :raise VMIPAddressMissingError: If no IP address is found for the the
                NIC's MAC address
        """
        def is_ip_reachable(ipaddr):
            res, _ = ping(ipaddr, timeout=5)
            return res == 0

        nic = self.virtnet[index]
        if nic.nettype == 'bridge':
            mac = self.get_mac_address()
            for mac_i in mac:
                ip = self.address_cache.get(mac_i)
                if ip and is_ip_reachable(ip):
                    return ip
            # TODO: Verify MAC-IP address mapping on remote ovirt node
            raise virt_vm.VMIPAddressMissingError(mac)
        else:
            raise ValueError("Ovirt only support bridge nettype now.")


class DataCenterManager(object):

    """
    This class handles all basic datacenter operations.
    """

    def __init__(self, params):
        self.name = params.get("dc_name", "")
        self.params = params
        (self.connection, self.version) = connect(params)
        self.dcs_service = self.connection.system_service().data_centers_service()

        if self.name:
            dc_search_result = self.dcs_service.list(search='name=%s' % self.name)
            if dc_search_result:
                self.instance = dc_search_result[0]

    def list(self):
        """
        List all of datacenters.
        """
        dc_list = []
        try:
            LOG.info('List Data centers')
            dcs = self.dcs_service.list(search='name=%s' % self.name)
            for i in range(len(dcs)):
                dc_list.append(dcs[i].name)
            return dc_list
        except Exception as e:
            LOG.error('Failed to get data centers:\n%s' % str(e))

    def add(self, storage_type):
        """
        Add a new data center.
        """
        if not self.name:
            self.name = "my_datacenter"
        try:
            LOG.info('Creating a %s type datacenter %s'
                     % (storage_type, self.name))
            if self.dcs_service.add(types.DataCenter(name=self.name, storage_type=storage_type, version=self.version)):
                LOG.info('Data center was created successfully')
        except Exception as e:
            LOG.error('Failed to create data center:\n%s' % str(e))


class ClusterManager(object):

    """
    This class handles all basic cluster operations.
    """

    def __init__(self, params):
        self.name = params.get("cluster_name", "")
        self.params = params
        (self.connection, self.version) = connect(params)
        self.clusters_service = self.connection.system_service().clusters_service()

        if self.name:
            self.instance = self.clusters_service.list(search='name=%s' % self.name)

    def list(self):
        """
        List all of clusters.
        """
        cluster_list = []
        try:
            LOG.info('List clusters')
            clusters = self.clusters_service.list()
            for i in range(len(clusters)):
                cluster_list.append(clusters[i].name)
            return cluster_list
        except Exception as e:
            LOG.error('Failed to get clusters:\n%s' % str(e))

    def add(self, dc_name, cpu_type='Intel Nehalem Family'):
        """
        Add a new cluster into data center.
        """
        if not self.name:
            self.name = "my_cluster"

        dc = self.connection.system_service().data_centers_service().list(search='name=%s' % dc_name)[0]
        try:
            LOG.info('Creating a cluster %s in datacenter %s'
                     % (self.name, dc_name))
            if self.clusters_service.add(types.Cluster(name=self.name,
                                                       cpu=types.CPU(id=cpu_type),
                                                       data_center=dc,
                                                       version=self.version)):
                LOG.info('Cluster was created successfully')
        except Exception as e:
            LOG.error('Failed to create cluster:\n%s' % str(e))


class HostManager(object):

    """
    This class handles all basic host operations.
    """

    def __init__(self, params):
        self.name = params.get("hostname", "")
        self.params = params
        (self.connection, self.version) = connect(params)
        self.hosts_service = self.connection.system_service().hosts_service()

        if self.name:
            self.instance = self.hosts_service.list(search='name=%s' % self.name)

    def list(self):
        """
        List all of hosts.
        """
        host_list = []
        try:
            LOG.info('List hosts')
            hosts = self.hosts_service.list()
            for i in range(len(hosts)):
                host_list.append(hosts[i].name)
            return host_list
        except Exception as e:
            LOG.error('Failed to get hosts:\n%s' % str(e))

    def state(self):
        """
        Return host state.
        """
        try:
            return self.instance.status.state
        except Exception as e:
            LOG.error('Failed to get %s status:\n%s' % (self.name, str(e)))

    def add(self, host_address, host_password, cluster_name, timeout=300):
        """
        Register a host into specified cluster.
        """
        end_time = time.time() + timeout
        if not self.name:
            self.name = 'my_host'

        clusters = self.connection.system_service().clusters_service().list(
            search='name=%s' % cluster_name)[0]
        host_params = types.Host(name=self.name, address=host_address,
                                 cluster=clusters, root_password=host_password)
        try:
            LOG.info('Registing a host %s into cluster %s'
                     % (self.name, cluster_name))
            if self.hosts_service.add(host_params):
                LOG.info('Waiting for host to reach the <Up> status ...')
                host_up = False
                while time.time() < end_time:
                    if self.state() == types.VmStatus.UP:
                        host_up = True
                        break
                    time.sleep(1)
                if not host_up:
                    raise WaitHostStateTimeoutError("UP", self.state())
                LOG.info('Host was installed successfully')
        except Exception as e:
            LOG.error('Failed to install host:\n%s' % str(e))

    def get_address(self):
        """
        Return host IP address.
        """
        try:
            LOG.info('Get host %s IP' % self.name)
            return self.instance.get_address()
        except Exception as e:
            LOG.error('Failed to get host %s IP address:\n%s' %
                      (self.name, str(e)))


class StorageDomainManager(object):

    """
    This class handles all basic storage domain operations.
    """

    def __init__(self, params):
        self.name = params.get("storage_name", "")
        self.params = params
        (self.connection, self.version) = connect(params)
        self.sds_service = self.connection.system_service().storage_domains_service()

        if self.name:
            self.instance = self.sds_service.list(search='name=%s' % self.name)

    def list(self):
        """
        List all of storagedomains.
        """
        storage_list = []
        try:
            LOG.info('List storage domains')
            storages = self.sds_service.list()
            for i in range(len(storages)):
                storage_list.append(storages[i].name)
            return storage_list
        except Exception as e:
            LOG.error('Failed to get storage domains:\n%s' % str(e))

    def attach_iso_export_domain_into_datacenter(self, address, path,
                                                 dc_name, host_name,
                                                 domain_type,
                                                 storage_type='nfs',
                                                 name='my_iso'):
        """
        Attach ISO/export domain into data center.

        :param name: ISO or Export name.
        :param host_name: host name.
        :param dc_name: data center name.
        :param path: ISO/export domain path.
        :param address: ISO/export domain address.
        :param domain_type: storage domain type, it may be 'iso' or 'export'.
        :param storage_type: storage type, it may be 'nfs', 'iscsi', or 'fc'.
        """
        dc = self.api.datacenters.get(dc_name)
        host = self.api.hosts.get(host_name)
        storage_params = types.Storage(type_=storage_type,
                                       address=address,
                                       path=path)

        storage_domain__params = types.StorageDomain(name=name,
                                                     data_center=dc,
                                                     type_=domain_type,
                                                     host=host,
                                                     storage=storage_params)

        try:
            LOG.info('Create/import ISO storage domain %s' % name)
            if self.api.storagedomains.add(storage_domain__params):
                LOG.info('%s domain was created/imported successfully'
                         % domain_type)

            LOG.info('Attach ISO storage domain %s' % name)
            if self.api.datacenters.get(dc_name).storagedomains.add(
                    self.api.storagedomains.get(name)):
                LOG.info('%s domain was attached successfully' % domain_type)

            LOG.info('Activate ISO storage domain %s' % name)
            if self.api.datacenters.get(dc_name).storagedomains.get(
                    name).activate():
                LOG.info('%s domain was activated successfully' % domain_type)
        except Exception as e:
            LOG.error('Failed to add %s domain:\n%s' % (domain_type, str(e)))
