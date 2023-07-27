import json
import logging

from virttest import utils_misc
# from virttest.vt_monitor.api import ConnectController

from ..compute_api import ComputeAPI
from ..migrate_api import MigrateAPI
from ..objects import instance_exception, instance_state, migration_exception, task
from ..objects.migrate_qemu_capabilities import QEMU_MIGRATION_CAPABILITIES
from ..objects.migrate_qemu_parameters import QEMU_MIGRATION_PARAMETERS
from ..objects.migration_state import MigrationState

LOG = logging.getLogger("avocado." + __name__)


class LiveMigrationTask(task.Task):
    def __init__(self, instance, destination, mig_config):
        """

        :param instance:
        :param destination:
        :param mig_config: The mig configuration for the migration
        """

        super(LiveMigrationTask, self).__init__(instance)
        self._source = instance.node
        self._destination = destination
        self._mig_config = mig_config
        self._migrate_api = MigrateAPI()
        self._compute_api = ComputeAPI()
        self._src_vmm_api = self._source.proxy.virt.vmm
        self._dst_vmm_api = self._destination.proxy.virt.vmm
        self._source_orig_caps = {}
        self._dest_orig_caps = {}
        self._source_orig_params = {}
        self._dest_orig_params = {}

    @property
    def destination(self):
        return self._destination

    def _check_source_instance_is_active(self):
        if self._instance.state not in (
            instance_state.States.RUNNING,
            instance_state.States.PAUSED,
        ):
            raise migration_exception.InstanceInvalidState()

    def _check_destination_is_not_source(self):
        if self._destination == self._source:
            raise migration_exception.UnableToMigrateToSelf()

    def _check_destination_has_enough_memory(self):
        return self._destination
        avail_mem = self._compute_api.get_avail_mem(self._destination)
        instance_mem = self._instance.spec["memory"]["machine"]["size"]
        if avail_mem <= instance_mem:
            reason = (
                f"Unable to migrate instance_id({self._instance.uuid}) "
                f"to dest({self._destination.name}): "
                f"Lack of memory(host:{avail_mem} <= instance:{instance_mem})"
            )
            raise migration_exception.MigrationPreCheckError(reason)

    def _check_compatible_hypervisor(self):
        return
        source_info = self._compute_api.get_hypervisor_info(self._source)
        dest_info = self._compute_api.get_hypervisor_info(self._destination)

        if source_info["type"] != dest_info["type"]:
            raise migration_exception.InvalidHypervisorType

        if source_info["version"] > dest_info["version"]:
            raise migration_exception.DestinationHypervisorTooOld

    def _check_requested_destination(self):
        """Performs basic pre-live migration checks for the forced host."""
        pass

    def prepare_migrate(self):
        """
        Prepare the environment to migrate from the source to destination.

        :return:
        """
        LOG.info("Preparing the migration task.")
        if self.status == MigrationState.ACCEPTED:
            self._check_source_instance_is_active()
            self._check_destination_is_not_source()
            self._check_destination_has_enough_memory()
            self._check_compatible_hypervisor()
            self._check_requested_destination()
            self.status = MigrationState.PRE_MIGRATING
        else:
            raise migration_exception.ExceptMigrationStatusError(
                MigrationState.ACCEPTED
            )

    def _monitor_migration(self):
        """
        Monitor the migration to record the status and
        information during migration.

        :return:
        """
        LOG.info("Starting to monitoring of the migration")

    def _migrate(self):
        """
        Migrate the instance by the hypervisor driver,
        e.g: qemu, libvirt, vmware, hyper.

        :return:
        """
        raise NotImplementedError

    def perform_migrate(self):
        """
        Start to migrate the instance from the source to the destination until
        it is completed.

        Raises:
            migration_exception.ExceptMigrationStatusError: _description_
        """
        LOG.info("Starting to execute the migration task.")
        if self.status == MigrationState.PRE_MIGRATING:
            self.status = MigrationState.MIGRATING
            self._migrate()
            self._monitor_migration()
            self.status = MigrationState.COMPLETED
        else:
            raise migration_exception.ExceptMigrationStatusError(
                MigrationState.PRE_MIGRATING
            )

    def post_migrate(self):
        """
        Post the environment of the migration.

        Raises:
            migration_exception.ExceptMigrationStatusError: _description_
        """
        LOG.info("Posting the migration task")
        if self.status == MigrationState.COMPLETED:
            self.status = MigrationState.POST_MIGRATING
            self._instance.node = self._destination
            # Switch the related resource from source to destination
            self.status = MigrationState.ACCEPTED
        else:
            raise migration_exception.ExceptMigrationStatusError(
                MigrationState.COMPLETED
            )

    def _execute(self):
        self.prepare_migrate()
        self.perform_migrate()
        self.post_migrate()

    def _cancel_migrate(self):
        raise NotImplementedError

    def cancel_migrate(self):
        LOG.info("Cancelling the migration task")
        if self.status == MigrationState.MIGRATING:
            self._cancel_migrate()
            self.status = MigrationState.ACCEPTED
        else:
            raise migration_exception.ExceptMigrationStatusError(
                MigrationState.MIGRATING
            )

    def pause_migrate(self):
        raise NotImplementedError

    def _resume_migrate(self):
        raise NotImplementedError

    def resume_migrate(self):
        LOG.info("Resuming the migration task")
        if self.status == MigrationState.PAUSED_MIGRATING:
            self._resume_migrate()
            self.status = MigrationState.MIGRATING
        else:
            raise migration_exception.ExceptMigrationStatusError(
                MigrationState.MIGRATING
            )

    def _get_migrate_info(self):
        raise NotImplementedError

    def get_migrate_info(self):
        LOG.info("Getting the information about current migration process")
        return self._get_migrate_info()


class LiveMigrationTaskQemu(LiveMigrationTask):
    def __init__(self, instance, destination, mig_config):
        """
        
        :param instance: 
        :param destination: 
        :param mig_config: the configuration for the migration
        {
            "flags": (), # e.g: [LIVE, OFFLINE, AUTO_CONVERGE, POSTCOPY, COMPRESSED, etc]
            "uri": {
                    "protocol": string, # e.g: tcp, rdma, unix, fd, etc
                    "address": string,
                    "port": integer,
                    },
            "capabilities": {
                            "source": {
                                        cap1: value1,
                                        cap2: value2,
                                        },
                            "destination": {
                                            cap1: value1,
                                            cap2: value2,
                                            },
                            },
            "parameters": {
                            "source": {
                                        param1: value1,
                                        param2: value2,
                                    },
                            "destination": {
                                            param1: value1,
                                            param2: value2,
                                            },
                        },
        }

        :type mig_config: dict

        """
        
        super(LiveMigrationTaskQemu, self).__init__(instance, destination, mig_config)
        # self._migration_flags = mig_config.get("flags")
        # self._migration_caps = MigrateCapabilities()
        # self._migration_params = mig_config.get("params")
        # self._migration_uri = None
        # if mig_config.get("monitor"):
        #     monitor = mig_config.get("monitor")
        # else:
        #     # Set the first monitor as the default
        #     monitor = instance.spec.get("monitors")[0]
        # self._monitor_controller = ConnectController(monitor, instance.id)
        # self._parse_migration_flags()

        # self._monitor_name = mig_config.get("monitor")
        # self._mon_controller = vt_monitor.MonitorController(instance,
        #                                                     self._monitor_name)

    # def _parse_migration_flag_post_copy(self):
    #     if self._mig_config.get("post_copy"):
    #         self._migration_flags.set_flag(QemuMigrateFlag.POST_COPY)
    #
    # def _parse_migration_flags(self):
    #     for flag in self._migration_flags:
    #         if flag in MigrateFlag:
    #             self._migration_caps.set_flag(flag)
    #         else:
    #             raise NotImplementedError("Not supported flag: %s" % flag)
    #     self._parse_migration_flag_post_copy()

    def _compare_cpu(self, guest_cpu_info, host_cpu_info):
        """Check the host is compatible with the requested CPU"""
        pass

    def _check_requested_destination(self):
        return
        guest_cpu_info = self._instance.spec["cpu"]
        host_cpu_info = self._compute_api.get_cpu_info(self._destination)
        self._compare_cpu(guest_cpu_info, host_cpu_info)

    def _begin_migrate(self):
        pass

    def _parse_migration_parameters(self):
        """
        Parse the migration parameters and capabilities from the migration
        config and flags.

        :return:
        """
        params = dict()
        params["source"] = self._mig_config.get("parameters").get("source")
        params["destination"] = self._mig_config.get("parameters").get("destination")

        return params

    def _parse_migrate_incoming(self):
        """
        Parse the URI for migrating from the migration configuration.

        :return:
        """
        incoming = dict()
        incoming["address"] = None
        incoming["uri"] = None
        incoming["fd"] = None
        incoming["path"] = None

        return incoming

    def _prepare_storage_destination(self):
        """
        Prepare the storage on the destination in advance,
        e.g: to prepare the volume by the storage management

        :return:
        """
        LOG.info("Preparing the storage on the destination")
        if MigrateFlag.NON_SHARED_DISK in self._migration_flags:
            # prepare the NBD storage server on the destination
            pass

    def _is_support_protocol_destination(self, protocol):
        return True

    def _prepare_incoming_destination(self, uri_params):
        protocol = uri_params.get("protocol")
        address = uri_params.get("address")
        port = uri_params.get("port")

        if not self._is_support_protocol_destination(protocol):
            raise ValueError(f"No support {protocol}")

        uri = None
        if protocol in ("tcp", "rdma", "x-rdma"):
            uri = f"{protocol}:{address}:{port}"
        elif protocol in ("unix",):
            uri = f"{protocol}:{address}"
        elif protocol in ("exec",):
            uri = f"{protocol}:{address}"
            raise NotImplementedError("Unsupported protocol exec")
        elif protocol in ("fd",):
            uri = f"{protocol}:{address}"

        incoming = dict()
        # Address where QEMU is supposed to listen
        incoming["address"] = address
        # Used when calling migrate-incoming QMP command
        incoming["uri"] = uri
        # # for fd:N URI
        # incoming["fd"] = fd

        return incoming

    def _create_instance_process_destination(self, migrate_incoming):
        """
        Create the instance process with "-incoming" on the destination.

        :return:
        """
        instance_uuid = self._instance.uuid
        instance_driver = self._instance.kind
        instance_spec = self._instance.spec
        self._dst_vmm_api.build_instance(
            instance_uuid, instance_driver, instance_spec, migrate_incoming
        )
        self._dst_vmm_api.run_instance(instance_uuid)

    def _check_migration_capabilities(self, node, mig_caps):
        # Check if the migration parameters are supported by the qemu driver
        capabilities = []
        for capability in mig_caps:
            if capability not in QEMU_MIGRATION_CAPABILITIES:
                raise ValueError(f"Unsupported qemu migration capabilities {capability}")
            capabilities.append(capability)

        # Get the capabilities on the node
        request = {"action": "query_capabilities",
                   "params": {"capabilities": capabilities}}
        orig_caps = node.proxy.virt.migration.handle_request(
            self._instance.uuid, request)
        LOG.debug(f"Get the original qemu capabilities:{orig_caps}")
        return orig_caps

    def _check_migration_parameters(self, node, mig_params):
        # Check if the migration parameters are supported by the qemu driver
        # And save those parameters to the migration task job.
        parameters = []
        for parameter in mig_params:
            if parameter not in QEMU_MIGRATION_PARAMETERS:
                raise ValueError(f"Unsupported migration parameter {parameter}")
            parameters.append(parameter)

            # Get the parameters on the node
        request = {
                    "action": "get_parameters",
                    "params": {"parameter": parameters}
                   }
        orig_params = node.proxy.virt.migration.handle_request(self._instance.uuid, request)
        LOG.debug(f"Get the original qemu parameters:{orig_params}")
        return orig_params


    def _save_migration_parameter(self, node, parameter):
        return {}

    def _apply_migration_capabilities(self, node, mig_caps):
        # Changing capabilities is only allowed before migration starts,
        # we need to skip them when resuming post-copy migration.

        # Apply the migration parameters value to the qemu driver
        for name, value in mig_caps.items():
            # parameters = PARAMETERS_INFO.get(name)
            if not name not in QEMU_MIGRATION_CAPABILITIES:
                raise ValueError(f"Unsupported migration parameter {name}")



    def _apply_migration_parameters(self):
        pass


    def _reset_migration_parameters(self, orig_params):
        pass

    def _start_nbd_server_destination(self):
        LOG.info("Start the NBD server")

    def _run_migration_destination(self, incoming_uri):
        LOG.info("Setting up incoming migration with URI %s", incoming_uri)

    def _prepare_migrate_destination(self):
        LOG.info(
            f"Preparing the migration of the instance({self.instance.uuid}) "
            f"on the destination:({self.destination}) "
        )
        mig_params = dict()
        mig_params["flags"] = self._mig_config.get("flags")
        mig_params["uri"] = self._mig_config.get("uri")
        capabilities = self._mig_config.get("capabilities")
        if capabilities:
            mig_params["capabilities"] = capabilities.get("destination")

        parameters = self._mig_config.get("parameters")
        if parameters:
            mig_params["parameters"] = parameters.get("destination")

        driver_kind = self._instance.kind
        spec = self._instance.spec
        return self._dst_vmm_api.migrate_instance_prepare(self._instance.uuid,
                                                          driver_kind, spec,
                                                          mig_params)
        # self._prepare_storage_destination()
        # mig_caps = self._migration_params.get("parameters")
        # mig_params = self._migration_params.get("parameters")
        # uri_params = self._migration_params.get("uri")
        # migrate_incoming = self._prepare_incoming_destination(uri_params)
        # incoming_uri = migrate_incoming.get("uri")
        #
        # LOG.info(f"Creating the VM instance process on "
        #          f"the destination with incoming URI: {incoming_uri}.")
        # self._create_instance_process_destination(migrate_incoming)
        #
        # self._dest_orig_caps.update(self._check_migration_capabilities(
        #     self.destination, mig_caps.keys()))
        # self._dest_orig_params.update(self._check_migration_parameters(
        #     self.destination, mig_params.keys()))
        #
        # try:
        #     self._apply_migration_capabilities(self.destination, mig_caps)
        #     self._apply_migration_parameters(self.destination, mig_params)
        #     if MigrateFlag.NON_SHARED_DISK in self._migration_caps:
        #         self._start_nbd_server_destination()
        #     self._run_migration_destination(migrate_incoming.get("uri"))
        # except Exception as e:
        #     LOG.error(e)
        #     self._reset_migration_parameters(self._orig_mig_params)
        #     self._dst_vmm_api.stop_instance(self._instance.uuid)

    def _copy_nbd_storage_source(self):
        LOG.info("Start to drive mirrors")

    def _parse_migrate_uri(self):
        return ""

    def _migrate_to_uri(self, uri):
        LOG.info(f"Migrating to {uri}")

    def _perform_migrate_source(self, migrate_incoming_uri):
        LOG.info(
            f"Performing the migration of the instance({self.instance.uuid}) "
            f"on the source:({self._source}) "
        )
        mig_params = dict()
        mig_params["flags"] = self._mig_config.get("flags")
        mig_params["uri"] = self._mig_config.get("uri")
        mig_params["uri"]["address"] = migrate_incoming_uri.get("address")
        if "port" in migrate_incoming_uri:
            mig_params["uri"]["port"] = migrate_incoming_uri.get("port")
        capabilities = self._mig_config.get("capabilities")
        if capabilities:
            mig_params["capabilities"] = capabilities.get("source")

        parameters = self._mig_config.get("parameters")
        if parameters:
            mig_params["parameters"] = parameters.get("source")

        mig_ret, mig_info = self._src_vmm_api.migrate_instance_perform(
            self._instance.uuid, mig_params)
        return mig_ret, json.loads(mig_info)

        # self._check_migration_parameters(self._migration_params)
        # _orig_mig_params = self._save_migration_parameters()
        # try:
        #     self._apply_migration_parameters(self._migration_params)
        #
        #     if QemuMigrateFlag.NON_SHARED_DISK in self._migration_flags:
        #         self._copy_nbd_storage_source()
        #
        #     uri = self._parse_migrate_uri()
        #     self._migrate_to_uri(uri)
        # except Exception as e:
        #     LOG.error(e)
        #     self._reset_migration_parameters(_orig_mig_params)

    def _mig_finished(self):
        pass

    def _is_alive_instance_destination(self):
        return True

    def _get_quit_error_msg(self):
        return ""

    def _finish_migrate_destination(self, mig_ret, timeout):
        LOG.info(
            f"Finishing the migration of the instance({self.instance.uuid}) "
            f"on the destination:({self.destination}) "
        )
        mig_params = dict()
        mig_params["flags"] = self._mig_config.get("flags")
        ret, mig_info = self._dst_vmm_api.migrate_instance_finish(
            self._instance.uuid, mig_ret, mig_params)
        mig_info = json.loads(mig_info)
        return ret, mig_info

    def _confirm_migrate_source(self, inmig_ret):
        LOG.info(
            f"Confirming the migration of the instance({self.instance.uuid}) "
            f"on the source:({self._source}) "
        )
        mig_params = dict()
        mig_params["flags"] = self._mig_config.get("flags")
        self._src_vmm_api.migrate_instance_confirm(self._instance.uuid,
                                                   inmig_ret, mig_params)

    def _migrate(self):
        # Dst: Get ready to accept incoming VM on the destination
        migrate_incoming_uri = self._prepare_migrate_destination()

        # Src: Start migration and wait for send completion
        mig_ret, mig_info = self._perform_migrate_source(migrate_incoming_uri)

        # Dst: Wait for recv completion and check status
        #      Kill off VM if failed, resume if success
        inmig_ret, inmig_info = self._finish_migrate_destination(
            mig_ret, timeout=1200)
        if not mig_ret:
            return False, mig_info

        # Src: Kill off VM if success, resume if failed
        self._confirm_migrate_source(inmig_ret)
        return True, mig_info

    def _cancel_migrate(self):
        self._src_vmm_api.migrate_instance_cancel(self._instance.uuid)

    def _resume_migrate(self):
        self._src_vmm_api.migrate_instance_resume(self._instance.uuid)

    def _get_migrate_info(self):
        return self._migrate_api.get_migrate_info(self._instance)


class LiveMigrationTaskLibvirt(LiveMigrationTask):
    def __init__(self, instance, destination, mig_config):
        super(LiveMigrationTaskLibvirt, self).__init__(
            instance, destination, mig_config
        )

    def _migrate(self):
        """
        Migrate the vm to another host by sending command
        e.g: "virsh migrate --live GuestName DestinationURL"
        """
        pass

    def _cancel_migrate(self):
        self._migrate_api.cancel_migration(self._instance)

    def _resume_migrate(self):
        self._migrate_api.resume_migration(self._instance)

    def _get_migrate_info(self):
        return self._migrate_api.get_migrate_info(self._instance)
