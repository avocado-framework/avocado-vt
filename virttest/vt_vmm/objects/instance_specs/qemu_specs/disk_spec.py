# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>


import logging
import six
import re

from virttest import qemu_storage
from virttest.qemu_capabilities import Flags
from virttest.qemu_devices import qdevices

try:
    from virttest.vt_imgr import vt_imgr
    from virttest.vt_resmgr import resmgr
    from virttest.vt_utils.image import qemu as qemu_image_utils
except ImportError:
    pass

from ..qemu_specs.spec import QemuSpec
from virttest.vt_vmm.objects.exceptions.instance_exception import InstanceSpecError


LOG = logging.getLogger("avocado." + __name__)



class QemuSpecDisk(QemuSpec):
    def __init__(self, vm_name, vm_params, node, disk_name):
        super(QemuSpecDisk, self).__init__(vm_name, vm_params, node)
        self._disk_name = disk_name
        self._parse_params()

    def _define_spec(self):
        """
        Define the specification of the disk

        :return: The specification of the disks.
                 Schema format:
                    {
                    "id": str,
                    "type": str,
                    # "controllers": [ # TODO: should move to the controller spec,
                                            but it is hard to do that since the
                                            HBA controllers are created by dynamically
                    #                 {
                    #                 "id": str,
                    #                 "bus": str,
                    #                 "type": str,
                    #                 "props": dict
                    #                 },
                    #             ]
                    "source": {
                                "id": str, #volume id
                                "type": str
                                "props": str,
                                "format": {
                                            "type": str
                                            "props": dict
                                        },
                                "backend": {
                                            "type": str,
                                            "props": dict,
                                        },
                                "slice":{
                                        "type": str
                                        "props": dict
                                    },
                                "auth": {
                                        "type": str
                                        "props": dict
                                },
                                "encrypt": {
                                        "type": str
                                        "props": dict
                                    },
                                "tls": {
                                        "type": str
                                        "props": dict
                                },
                                "httpcookie": {
                                        "type": str
                                        "props": dict
                                },
                            },
                    "filter": [
                            {
                              "type": str,
                              "props": dict
                            },
                    ]
                    "device": {
                                "id": str,
                                "type": str,
                                "bus": { # the hba controller spec
                                        "type": str,
                                        "props": dict,
                                        }
                                "props": dict
                            },
                    }
        """
        def __define_spec_by_variables(
            name,
            filename,
            pci_bus,
            index=None,
            fmt=None,
            cache=None,
            werror=None,
            rerror=None,
            serial=None,
            snapshot=None,
            boot=None,
            blkdebug=None,
            bus=None,
            unit=None,
            port=None,
            bootindex=None,
            removable=None,
            min_io_size=None,
            opt_io_size=None,
            physical_block_size=None,
            logical_block_size=None,
            readonly=None,
            scsiid=None,
            lun=None,
            aio=None,
            strict_mode=None,
            media=None,
            imgfmt=None,
            pci_addr=None,
            scsi_hba=None,
            iothread=None,
            blk_extra_params=None,
            scsi=None,
            drv_extra_params=None,
            num_queues=None,
            bus_extra_params=None,
            force_fmt=None,
            image_encryption=None,
            image_access=None,
            external_data_file=None,
            image_throttle_group=None,
            image_auto_readonly=None,
            image_discard=None,
            image_copy_on_read=None,
            image_iothread_vq_mapping=None,
            slices_info=None,
        ):
            # def _get_access_tls_creds(image_access):
            #     """Get all tls-creds objects of the image and its backing images"""
            #     tls_creds = []
            #     if image_access is not None:
            #         creds_list = []
            #         if image_access.image_backing_auth:
            #             creds_list.extend(
            #                 image_access.image_backing_auth.values())
            #         if image_access.image_auth:
            #             creds_list.append(image_access.image_auth)
            #
            #         for creds in creds_list:
            #             if creds.storage_type == "nbd":
            #                 if creds.tls_creds:
            #                     tls_creds.append(creds)
            #
            #     return tls_creds
            #
            # def _get_access_secrets(image_access):
            #     """Get all secret objects of the image and its backing images"""
            #     secrets = []
            #     if image_access is not None:
            #         access_info = []
            #
            #         # backing images' access objects
            #         if image_access.image_backing_auth:
            #             access_info.extend(
            #                 image_access.image_backing_auth.values())
            #
            #         # image's access object
            #         if image_access.image_auth is not None:
            #             access_info.append(image_access.image_auth)
            #
            #         for access in access_info:
            #             if access.storage_type == "ceph":
            #                 # Now we use 'key-secret' for both -drive and -blockdev,
            #                 # but for -drive, 'password-secret' also works, add an
            #                 # option in cfg file to enable 'password-secret' in future
            #                 if access.data:
            #                     secrets.append((access, "key"))
            #             elif access.storage_type == "iscsi-direct":
            #                 if Flags.BLOCKDEV in self.caps:
            #                     # -blockdev: only password-secret is supported
            #                     if access.data:
            #                         secrets.append((access, "password"))
            #                 else:
            #                     # -drive: u/p included in the filename
            #                     pass
            #             elif access.storage_type == "curl":
            #                 if access.cookie:
            #                     secrets.append((access.cookie, "cookie"))
            #
            #                 if Flags.BLOCKDEV in self.caps:
            #                     # -blockdev requires password-secret while
            #                     # -drive includes u/p in the filename
            #                     if access.data:
            #                         secrets.append((access, "password"))
            #
            #     return secrets

            disk = dict()
            disk_props = dict()

            # controller = dict()
            # controller_props = dict()

            source = dict()
            source_props = dict()
            source_format = dict()
            source_format_props = dict()
            source_backend = dict()
            source_backend_props = dict()
            source_slice = dict
            source_slice_props = dict()
            source_auth = dict()
            source_auth_props = dict()
            source_encrypt = dict()
            source_encrypt_props = dict()
            source_tls = dict()
            source_tls_props = dict()

            source_filters = list()
            source_filter = dict()
            source_filter_props = dict()

            device = dict()
            device_bus = dict()
            device_bus_props = dict()
            device_bus["props"] = device_bus_props
            device_props = dict()

            #
            # Parse params
            #
            # devices = []  # All related devices


            # FIXME: skip it
            # add required secret objects for image
            # secret_obj = None
            # if image_encryption:
            #     for secret in image_encryption.image_key_secrets:
            #         devices.append(qdevices.QObject("secret"))
            #         devices[-1].set_param("id", secret.aid)
            #         devices[-1].set_param("data", secret.data)
            #     if image_encryption.key_secret:
            #         secret_obj = devices[-1]
            #
            # secret_info = []
            # image_secrets = _get_access_secrets(image_access)
            # for sec, sectype in image_secrets:
            #     # create and add all secret objects: -object secret
            #     devices.append(qdevices.QObject("secret"))
            #     devices[-1].set_param("id", sec.aid)
            #     devices[-1].set_param("format", sec.data_format)
            #
            #     if sectype == "password":
            #         devices[-1].set_param("file", sec.filename)
            #     elif sectype == "key" or sectype == "cookie":
            #         devices[-1].set_param("data", sec.data)
            #
            #     if sec.image == name:
            #         # only the top image should be associated
            #         # with its secure object
            #         secret_info.append((devices[-1], sectype))
            #
            # tls_creds = None
            # tls_creds_obj = None
            # creds_list = _get_access_tls_creds(image_access)
            # for creds in creds_list:
            #     # create and add all tls-creds objects
            #     devices.append(qdevices.QObject("tls-creds-x509"))
            #     devices[-1].set_param("id", creds.aid)
            #     devices[-1].set_param("endpoint", "client")
            #     devices[-1].set_param("dir", creds.tls_creds)
            #
            #     if creds.image == name:
            #         # only the top image should be associated
            #         # with its tls-creds object
            #         tls_creds_obj = devices[-1]
            #         tls_creds = creds
            #
            # iscsi_initiator = None
            # gluster_debug = None
            # gluster_logfile = None
            # gluster_peers = {}
            # reconnect_delay = None
            # curl_sslverify = None
            # curl_readahead = None
            # curl_timeout = None
            # access = image_access.image_auth if image_access else None
            # if access is not None:
            #     if access.storage_type == "iscsi-direct":
            #         iscsi_initiator = access.iscsi_initiator
            #     elif access.storage_type == "glusterfs-direct":
            #         gluster_debug = access.debug
            #         gluster_logfile = access.logfile
            #
            #         peers = []
            #         for peer in access.peers:
            #             if "path" in peer:
            #                 # access storage by unix domain socket
            #                 peers.append(
            #                     {"type": "unix", "path": peer["path"]})
            #             else:
            #                 # access storage by hostname/ip + port
            #                 peers.append(
            #                     {
            #                         "host": peer["host"],
            #                         "type": peer.get("type", "inet"),
            #                         "port": "%s" % peer.get("port", "0"),
            #                     }
            #                 )
            #         gluster_peers.update(
            #             {
            #                 "server.{i}.{k}".format(i=i + 1, k=k): v
            #                 for i, server in enumerate(peers)
            #                 for k, v in six.iteritems(server)
            #             }
            #         )
            #     elif access.storage_type == "nbd":
            #         reconnect_delay = access.reconnect_delay
            #     elif access.storage_type == "curl":
            #         curl_sslverify = access.sslverify
            #         curl_timeout = access.timeout
            #         curl_readahead = access.readahead

            use_device = self._has_option("device")
            if fmt == "scsi":  # fmt=scsi force the old version of devices
                LOG.warning(
                    "'scsi' drive_format is deprecated, please use the "
                    "new lsi_scsi type for disk %s",
                    name,
                )
                use_device = False
            if not fmt:
                use_device = False
            if fmt == "floppy" and not self._has_option("global"):
                use_device = False

            if strict_mode is None:
                strict_mode = self.strict_mode
            if strict_mode:  # Force default variables
                if cache is None:
                    cache = "none"
                if removable is None:
                    removable = "yes"
                if aio is None:
                    aio = "native"
                if media is None:
                    media = "disk"
            else:  # Skip default variables
                if media != "cdrom":  # ignore only 'disk'
                    media = None

            if "[,boot=on|off]" not in self._qemu_help:
                if boot in ("yes", "on", True):
                    bootindex = "1"
                boot = None

            bus = self._none_or_int(bus)  # First level
            unit = self._none_or_int(unit)  # Second level
            port = self._none_or_int(port)  # Third level
            # Compatibility with old params - scsiid, lun
            if scsiid is not None:
                LOG.warning(
                    "drive_scsiid param is obsolete, use drive_unit " "instead (disk %s)",
                    name,
                )
                unit = self._none_or_int(scsiid)
            if lun is not None:
                LOG.warning(
                    "drive_lun param is obsolete, use drive_port instead " "(disk %s)",
                    name
                )
                port = self._none_or_int(lun)
            if pci_addr is not None and fmt == "virtio":
                LOG.warning(
                    "drive_pci_addr is obsolete, use drive_bus instead " "(disk %s)",
                    name
                )
                bus = self._none_or_int(pci_addr)

            arch = self._node.proxy.platform.get_arch()

            # Define the controller spec
            #
            # HBA
            # fmt: ide, scsi, virtio, scsi-hd, ahci, usb1,2,3 + hba
            # device: ide-drive, usb-storage, scsi-hd, scsi-cd, virtio-blk-pci
            # bus: ahci, virtio-scsi-pci, USB
            #
            if not use_device:
                pass
                # TODO: support the drive mode
                # if fmt and (
                #         fmt == "scsi"
                #         or (
                #                 fmt.startswith("scsi")
                #                 and (
                #                         scsi_hba == "lsi53c895a" or scsi_hba == "spapr-vscsi")
                #         )
                # ):
                #     if not (bus is None and unit is None and port is None):
                #         LOG.warning(
                #             "Using scsi interface without -device "
                #             "support; ignoring bus/unit/port. (%s)",
                #             name,
                #         )
                #         source_props["bus"] = None
                #         source_props["unit"] = None
                #         source_props["port"] = None
                #     # In case we hotplug, lsi wasn't added during the startup hook
                #     if arch in ("ppc64", "ppc64le"):
                #         controller["type"] = "spapr-vscsi"
                #         controller["bus"] = None
                #         controller_props["bus"] = None
                #         controller_props["unit"] = None
                #         controller_props["port"] = None
                #     else:
                #         controller["type"] = "lsi53c895a"
                #         controller["bus"] = pci_bus
                #         controller_props["bus"] = None
                #         controller_props["unit"] = None
                #         controller_props["port"] = None
            elif fmt == "ide":
                if bus:
                    LOG.warning(
                        "ide supports only 1 hba, use drive_unit to set"
                        "ide.* for disk %s",
                        name,
                    )
                bus = unit
                device_bus["type"] = "ide"
            elif fmt == "ahci":
                pass
                # devices.extend(devs)
            elif fmt.startswith("scsi-"):
                if not scsi_hba:
                    scsi_hba = "virtio-scsi-pci"
                if scsi_hba != "virtio-scsi-pci":
                    num_queues = None
                addr_spec = None
                if scsi_hba == "lsi53c895a":
                    addr_spec = [8, 16384]
                elif scsi_hba.startswith("virtio"):
                    addr_spec = [256, 16384]
                    if scsi_hba == "virtio-scsi-device":
                        pci_bus = "virtio-bus"
                    elif scsi_hba == "virtio-scsi-ccw":
                        pci_bus = None
                elif scsi_hba == "spapr-vscsi":
                    addr_spec = [64, 32]
                    pci_bus = None
                device_bus["type"] = scsi_hba
                device_bus["bus"] = pci_bus
                # device_bus_props["bus"] = bus
                # device_bus_props["unit"] = unit
                # device_bus_props["port"] = port
                device_bus_props["num_queues"] = num_queues
                device_bus_props["addr_spec"] = addr_spec
                if bus_extra_params:
                    for extra_param in bus_extra_params.split(","):
                        key, value = extra_param.split("=")
                        device_bus_props[key] = value
                # devices.extend(_)
            elif fmt in ("usb1", "usb2", "usb3"):
                if bus:
                    LOG.warning(
                        "Manual setting of drive_bus is not yet supported"
                        " for usb disk %s",
                        name,
                    )
                    bus = None
                if fmt == "usb1":
                    pass
                    # dev_parent = {"type": "uhci"}
                    # if arch.ARCH in ("ppc64", "ppc64le"):
                    #     dev_parent = {"type": "ohci"}
                elif fmt == "usb2":
                    pass
                    # dev_parent = "ehci"
                elif fmt == "usb3":
                    pass
                    # dev_parent = {"type": "xhci"}
            elif fmt == "virtio":
                pass
                # dev_parent = pci_bus
            elif fmt == "virtio-blk-device":
                pass
                # dev_parent = {"type": "virtio-bus"}
            elif fmt == "virtio-blk-ccw":  # For IBM s390 platform
                pass
                # dev_parent = {"type": "virtual-css"}
            else:
                pass
                # dev_parent = {"type": fmt}

            # Define the source spec
            #
            # Drive mode:
            # -drive fmt or -drive fmt=none -device ...
            # Blockdev mode:
            # -blockdev node-name ... -device ...
            #
            if Flags.BLOCKDEV in self._qemu_caps:
                protocol_cls = qdevices.QBlockdevProtocolFile
                if not filename:
                    protocol_cls = qdevices.QBlockdevProtocolNullCo
                elif filename.startswith("iscsi:"):
                    protocol_cls = qdevices.QBlockdevProtocolISCSI
                elif filename.startswith("rbd:"):
                    protocol_cls = qdevices.QBlockdevProtocolRBD
                elif filename.startswith("gluster"):
                    protocol_cls = qdevices.QBlockdevProtocolGluster
                elif re.match(r"nbd(\+\w+)?://", filename):
                    protocol_cls = qdevices.QBlockdevProtocolNBD
                elif filename.startswith("nvme:"):
                    protocol_cls = qdevices.QBlockdevProtocolNVMe
                elif filename.startswith("ssh:"):
                    protocol_cls = qdevices.QBlockdevProtocolSSH
                elif filename.startswith("https:"):
                    protocol_cls = qdevices.QBlockdevProtocolHTTPS
                elif filename.startswith("http:"):
                    protocol_cls = qdevices.QBlockdevProtocolHTTP
                elif filename.startswith("ftps:"):
                    protocol_cls = qdevices.QBlockdevProtocolFTPS
                elif filename.startswith("ftp:"):
                    protocol_cls = qdevices.QBlockdevProtocolFTP
                elif filename.startswith("vdpa:"):
                    protocol_cls = qdevices.QBlockdevProtocolVirtioBlkVhostVdpa
                elif fmt in ("scsi-generic", "scsi-block"):
                    protocol_cls = qdevices.QBlockdevProtocolHostDevice
                elif blkdebug is not None:
                    protocol_cls = qdevices.QBlockdevProtocolBlkdebug

                if imgfmt == "qcow2":
                    format_cls = qdevices.QBlockdevFormatQcow2
                elif imgfmt == "raw" or media == "cdrom":
                    format_cls = qdevices.QBlockdevFormatRaw
                elif imgfmt == "luks":
                    format_cls = qdevices.QBlockdevFormatLuks
                elif imgfmt == "nvme":
                    format_cls = qdevices.QBlockdevFormatRaw
                elif imgfmt is None:
                    # use RAW type as the default
                    format_cls = qdevices.QBlockdevFormatRaw

                # vt_images = self._env.get_vm_images(self._name)
                # for image in vt_images:
                #     if image.tag == image_name:
                #         source["id"] = image.uuid
                #         image_info = vt_image.api.get_info(image.uuid)
                #         volume_id = image_info.get("volume_id")
                #         source["id"] = "volume1"
                # disk["source"] = "volume_%s" % image_name
                source["id"] = name
                source["type"] = protocol_cls.TYPE
                top_node = "protocol_node"

                need_format_node = format_cls is not qdevices.QBlockdevFormatRaw
                need_format_node |= Flags.BLOCKJOB_BACKING_MASK_PROTOCOL not in self._qemu_caps
                need_format_node |= slices_info is not None and bool(
                    slices_info.slices)
                format_node = None
                if need_format_node:
                    source_format["type"] = format_cls.TYPE
                    top_node = "format_node"
                # Add filter node
                if image_copy_on_read in ("yes", "on", "true"):
                    source_filter["type"] = qdevices.QBlockdevFilterCOR.TYPE
                    source_filters.append(source_filter)

                if image_throttle_group:
                    source_filter["type"] = qdevices.QBlockdevFilterThrottle.TYPE
                    source_filters.append(source_filter)
            # else: # FIXME: skip the drive mode
                # if self.has_hmp_cmd("__com.redhat_drive_add") and use_device:
                #     devices.append(qdevices.QRHDrive(name))
                # elif self.has_hmp_cmd("drive_add") and use_device:
                #     devices.append(qdevices.QHPDrive(name))
                # elif self.has_option("device"):
                #     devices.append(qdevices.QDrive(name, use_device))
                # else:  # very old qemu without 'addr' support
                #     devices.append(qdevices.QOldDrive(name, use_device))

            if Flags.BLOCKDEV in self._qemu_caps:
                for opt, val in zip(("serial", "boot"), (serial, boot)):
                    if val is not None:
                        LOG.warning(
                            "The command line option %s is not supported "
                            "on %s by -blockdev." % (opt, name)
                        )
                if media == "cdrom":
                    readonly = "on"

                if top_node == "protocol_node":
                    source_props["read-only"] = readonly
                elif top_node == "format_node":
                    source_format_props["read-only"] = readonly

                if top_node != "protocol_node":
                    source_props["auto-read-only"] = image_auto_readonly
                source_props["discard"] = image_discard

                if slices_info is not None and len(slices_info.slices) > 0:
                    source_format_props["offset"] = slices_info.slices[0].offset
                    source_format_props["size"] = slices_info.slices[0].size

                # if secret_obj:
                #     if source_format.get("type") == qdevices.QBlockdevFormatQcow2.TYPE:
                #         source_format_props["encrypt.format"] = image_encryption.format
                #         source_format_props["encrypt.key-secret"] = secret_obj.get_qid()
                #     elif source_format.get("type") == qdevices.QBlockdevFormatLuks.TYPE:
                #         source_format_props["key-secret"] = secret_obj.get_qid()

            # else: # FIXME: skip this part for drive mode
                # devices[-1].set_param("if", "none")
                # devices[-1].set_param("rerror", rerror)
                # devices[-1].set_param("werror", werror)
                # devices[-1].set_param("serial", serial)
                # devices[-1].set_param("boot", boot, bool)
                # devices[-1].set_param("snapshot", snapshot, bool)
                # devices[-1].set_param("readonly", readonly, bool)
                # if secret_obj:
                #     if imgfmt == "qcow2":
                #         devices[-1].set_param("encrypt.format",
                #                               image_encryption.format)
                #         devices[-1].set_param("encrypt.key-secret",
                #                               secret_obj.get_qid())
                #     elif imgfmt == "luks":
                #         devices[-1].set_param("key-secret",
                #                               secret_obj.get_qid())
            # FIXME: skip this part for drive mode
            # external_data_file_path = getattr(external_data_file,
            #                                   "image_filename", None)
            # if external_data_file_path:
            #     # by now we only support local files
            #     ext_data_file_driver = "file"
            #
            #     # check if the data file is a block device
            #     if ext_data_file_driver == "file":
            #         ext_data_file_mode = os.stat(
            #             external_data_file_path).st_mode
            #         if stat.S_ISBLK(ext_data_file_mode):
            #             ext_data_file_driver = "host_device"
            #     devices[-1].set_param("data-file.driver", ext_data_file_driver)
            #     devices[-1].set_param("data-file.filename",
            #                           external_data_file_path)

            if "aio" in self._qemu_help:
                if aio == "native" and snapshot == "yes":
                    LOG.warning("snapshot is on, fallback aio to threads.")
                    aio = "threads"
                if Flags.BLOCKDEV in self._qemu_caps:
                    if source.get("type") in (
                                    qdevices.QBlockdevProtocolFile,
                                    qdevices.QBlockdevProtocolHostDevice,
                                    qdevices.QBlockdevProtocolHostCdrom,
                            ):
                        source_props["aio"] = aio
                # FIXME: skip this part for drive mode
                # else:
                #     devices[-1].set_param("aio", aio)
                if aio == "native":
                    # Since qemu 2.6, aio=native has no effect without
                    # cache.direct=on or cache=none, It will be error out.
                    # Please refer to qemu commit d657c0c.
                    cache = cache not in ["none",
                                          "directsync"] and "none" or cache
            # Forbid to specify the cache mode for empty drives.
            # More info from qemu commit 91a097e74.
            if not filename:
                cache = None
            elif filename.startswith("nvme://"):
                # NVMe controller doesn't support write cache configuration
                cache = "writethrough"
            if Flags.BLOCKDEV in self._qemu_caps:
                if filename:
                    file_opts = qemu_storage.filename_to_file_opts(filename)
                    for key, value in six.iteritems(file_opts):
                        source_props[key] = value
                #
                # for access_secret_obj, secret_type in secret_info:
                #     if secret_type == "password":
                #         protocol_node.set_param(
                #             "password-secret", access_secret_obj.get_qid()
                #         )
                #     elif secret_type == "key":
                #         protocol_node.set_param("key-secret",
                #                                 access_secret_obj.get_qid())
                #     elif secret_type == "cookie":
                #         protocol_node.set_param(
                #             "cookie-secret", access_secret_obj.get_qid()
                #         )
                #
                # if tls_creds is not None:
                #     protocol_node.set_param("tls-creds",
                #                             tls_creds_obj.get_qid())
                # if reconnect_delay is not None:
                #     protocol_node.set_param("reconnect-delay",
                #                             int(reconnect_delay))
                # if iscsi_initiator:
                #     protocol_node.set_param("initiator-name", iscsi_initiator)
                # if gluster_debug:
                #     protocol_node.set_param("debug", int(gluster_debug))
                # if gluster_logfile:
                #     protocol_node.set_param("logfile", gluster_logfile)
                # if curl_sslverify:
                #     protocol_node.set_param("sslverify", curl_sslverify)
                # if curl_readahead:
                #     protocol_node.set_param("readahead", curl_readahead)
                # if curl_timeout:
                #     protocol_node.set_param("timeout", curl_timeout)
                # for key, value in six.iteritems(gluster_peers):
                #     protocol_node.set_param(key, value)

                if not cache:
                    direct, no_flush = (None, None)
                else:
                    direct, no_flush = (
                        self.cache_map[cache]["cache.direct"],
                        self.cache_map[cache]["cache.no-flush"],
                    )
                source_props["cache.direct"] = direct
                source_format_props["cache.direct"] = direct
                source_props["cache.no-flush"] = no_flush
                source_format_props["cache.no-flush"] = no_flush

                # if top_node is not protocol_node:
                #     top_node.set_param("file", protocol_node.get_qid())
            # FIXME: skip this part for drive mode
            # else:
            #     devices[-1].set_param("cache", cache)
            #     devices[-1].set_param("media", media)
            #     devices[-1].set_param("format", imgfmt)
            #     if blkdebug is not None:
            #         devices[-1].set_param("file", "blkdebug:%s:%s" % (
            #         blkdebug, filename))
            #     else:
            #         devices[-1].set_param("file", filename)
            #
            #     for access_secret_obj, secret_type in secret_info:
            #         if secret_type == "password":
            #             devices[-1].set_param(
            #                 "file.password-secret", access_secret_obj.get_qid()
            #             )
            #         elif secret_type == "key":
            #             devices[-1].set_param(
            #                 "file.key-secret", access_secret_obj.get_qid()
            #             )
            #         elif secret_type == "cookie":
            #             devices[-1].set_param(
            #                 "file.cookie-secret", access_secret_obj.get_qid()
            #             )
            #
            #     if tls_creds is not None:
            #         devices[-1].set_param("file.tls-creds",
            #                               tls_creds_obj.get_qid())
            #     if reconnect_delay is not None:
            #         devices[-1].set_param("file.reconnect-delay",
            #                               int(reconnect_delay))
            #     if iscsi_initiator:
            #         devices[-1].set_param("file.initiator-name",
            #                               iscsi_initiator)
            #     if gluster_debug:
            #         devices[-1].set_param("file.debug", int(gluster_debug))
            #     if gluster_logfile:
            #         devices[-1].set_param("file.logfile", gluster_logfile)
            #     if curl_sslverify:
            #         devices[-1].set_param("file.sslverify", curl_sslverify)
            #     if curl_readahead:
            #         devices[-1].set_param("file.readahead", curl_readahead)
            #     if curl_timeout:
            #         devices[-1].set_param("file.timeout", curl_timeout)

            if drv_extra_params:
                drv_extra_params = (
                    _.split("=", 1) for _ in drv_extra_params.split(",") if _
                )
                for key, value in drv_extra_params:
                    if Flags.BLOCKDEV in self._qemu_caps:
                        if key == "discard":
                            value = re.sub("on", "unmap",
                                           re.sub("off", "ignore", value))
                        if key in ("cache-size",):
                            source_props[key] = None
                        else:
                            source_props[key] = value
                        if source_format is not None:
                            source_format_props[key] = value
                            # suppress key if format_node presents
                            if key in ("detect-zeroes",):
                                source_props[key] = None
                    # FIXME: skip this part for drive mode
                    # else:
                    #     devices[-1].set_param(key, value)

            # TODO: support the drive mode
            # if not use_device:
            #     if fmt and fmt.startswith("scsi-"):
            #         if scsi_hba == "lsi53c895a" or scsi_hba == "spapr-vscsi":
            #             fmt = "scsi"  # Compatibility with the new scsi
            #     if fmt and fmt not in (
            #             "ide",
            #             "scsi",
            #             "sd",
            #             "mtd",
            #             "floppy",
            #             "pflash",
            #             "virtio",
            #     ):
            #         raise virt_vm.VMDeviceNotSupportedError(self.vmname, fmt)
            #     devices[-1].set_param("if",
            #                           fmt)  # overwrite previously set None
            #     if not fmt:  # When fmt unspecified qemu uses ide
            #         fmt = "ide"
            #     devices[-1].set_param("index", index)
            #     if fmt == "ide":
            #         devices[-1].parent_bus = (
            #         {"type": fmt.upper(), "atype": fmt},)
            #     elif fmt == "scsi":
            #         if arch.ARCH in ("ppc64", "ppc64le"):
            #             devices[-1].parent_bus = (
            #             {"atype": "spapr-vscsi", "type": "SCSI"},)
            #         else:
            #             devices[-1].parent_bus = (
            #             {"atype": "lsi53c895a", "type": "SCSI"},)
            #     elif fmt == "floppy":
            #         devices[-1].parent_bus = ({"type": fmt},)
            #     elif fmt == "virtio":
            #         devices[-1].set_param("addr", pci_addr)
            #         devices[-1].parent_bus = (pci_bus,)
            #     if not media == "cdrom":
            #         LOG.warning(
            #             "Using -drive fmt=xxx for %s is unsupported "
            #             "method, false errors might occur.",
            #             name,
            #         )
            #     disk["type"] = media
            #     return disk
            disk["id"] = name
            disk["type"] = media

            # Define the device spec
            #
            # Device
            #
            device["id"] = name
            # FIXME: workaround for this part by using dev_parent as the device bus
            device["bus"] = device_bus
            if fmt in ("ide", "ahci"):
                if not self._has_device("ide-hd"):
                    device["type"] = "ide-drive"
                elif media == "cdrom":
                    device["type"] = "ide-cd"
                else:
                    device["type"] = "ide-hd"
                device_props["unit"] = port
            elif fmt and fmt.startswith("scsi-"):
                device["type"] = fmt
                device_props["scsi-id"] = unit
                device_props["lun"] = unit
                device_props["removable"] = removable

                if strict_mode:
                    device_props["channel"] = 0

            elif fmt == "virtio":
                device["type"] = "virtio-blk-pci"
                device_props["scsi"] = scsi
                if bus is not None:
                    device_props["addr"] = bus
                    bus = None
                # TODO: support it in the future
                # if iothread:
                #     try:
                #         iothread = self.allocate_iothread(iothread, devices[-1])
                #     except TypeError:
                #         pass
                #     else:
                #         if iothread and iothread not in self:
                #             devices.insert(-2, iothread)
            elif fmt in ("usb1", "usb2", "usb3"):
                device["type"] = "usb-storage"
                device_props["port"] = unit
                device_props["removable"] = removable
            elif fmt == "floppy":
                device["type"] = "floppy"
                device_props["unit"] = unit
                device_bus["type"] = "floppy"
                device_bus["id"] = "drive_%s" % name

            else:
                LOG.warning("Using default device handling (disk %s)", name)
                device["type"] = fmt
            if force_fmt:
                LOG.info("Force to use %s for the device" % force_fmt)
                device["type"] = force_fmt
            # Get the supported options
            options = self._node.proxy.virt.tools.qemu.get_help_info("-device %s," % device["type"])
            device_props["bus"] = bus # 1st level of disk location (index of bus) ($int), bus:unit:port
            device_props["drive"] = "drive_%s" % name
            device_props["logical_block_size"] = logical_block_size
            device_props["physical_block_size"] = physical_block_size
            device_props["min_io_size"] = min_io_size
            device_props["opt_io_size"] = opt_io_size
            device_props["bootindex"] = bootindex
            if Flags.BLOCKDEV in self._qemu_caps:
                if source["type"] == qdevices.QBlockdevProtocolHostDevice.TYPE:
                    self.cache_map[cache]["write-cache"] = None
                write_cache = None if not cache else self.cache_map[cache]["write-cache"]
                device_props["write-cache"] = write_cache
                if "scsi-generic" == fmt:
                    rerror, werror = (None, None)
                device_props["rerror"] = rerror
                device_props["werror"] = werror
            if "serial" in options:
                device_props["serial"] = serial
                if need_format_node:
                    source_format_props["serial"] = serial
                source_props["serial"] = serial
            if blk_extra_params:
                blk_extra_params = (
                    _.split("=", 1) for _ in blk_extra_params.split(",") if _
                )
                for key, value in blk_extra_params:
                    device_props[key] = value
            # if self.is_dev_iothread_vq_supported(devices[-1]):
            #     if num_queues:
            #         devices[-1].set_param("num-queues", num_queues)
            #     # add iothread-vq-mapping if available
            #     if image_iothread_vq_mapping:
            #         val = []
            #         for item in image_iothread_vq_mapping.strip().split(" "):
            #             allocated_iothread = self.allocate_iothread_vq(
            #                 item.split(":")[0], devices[-1]
            #             )
            #             mapping = {"iothread": allocated_iothread.get_qid()}
            #             if len(item.split(":")) == 2:
            #                 vqs = [int(_) for _ in item.split(":")[-1].split(",")]
            #                 mapping["vqs"] = vqs
            #             val.append(mapping)
            #         # FIXME: The reason using set_param() is that the format(
            #         #  Example: iothread0:0,1,2 ) can NOT be set by
            #         #  Devcontainer.insert() appropriately since the contents
            #         #  following after colon are lost.
            #         if ":" in image_iothread_vq_mapping:
            #             devices[-1].set_param("iothread-vq-mapping", val)
            #
            #     if isinstance(
            #         self.iothread_manager, vt_iothread.MultiPeerRoundRobinManager
            #     ):
            #         mapping = self.iothread_manager.pci_dev_iothread_vq_mapping
            #         if devices[-1].get_qid() in mapping:
            #             num_iothread = len(mapping[devices[-1].get_qid()])
            #             for i in range(num_iothread):
            #                 iothread = self.allocate_iothread_vq("auto", devices[-1])
            #                 iothread.iothread_vq_bus.insert(devices[-1])
            #     elif isinstance(self.iothread_manager, vt_iothread.FullManager):
            #         iothreads = self.allocate_iothread_vq("auto", devices[-1])
            #         if iothreads:
            #             for ioth in iothreads:
            #                 ioth.iothread_vq_bus.insert(devices[-1])
            # controller["props"] = controller_props
            # disk["controller"] = controller

            source["props"] = source_props

            source_format["props"] = source_format_props
            source["format"] = source_format

            disk["source"] = source

            device["bus"] = device_bus
            device["props"] = device_props
            disk["device"] = device

            return disk

        image_name = self._disk_name
        media = "disk"
        image_id = vt_imgr.query_image(image_name, self._name)
        image_info = vt_imgr.get_image_info(image_id)
        # FIXME: Use qemu_devices for handling indexes
        image_params = self._params.object_params(image_name)
        # if image_params.get("boot_drive") == "no":
        #     return {}
        if self._params.get("index_enable") == "yes":
            drive_index = image_params.get("drive_index")
            if drive_index:
                index = drive_index
            else:
                self._last_driver_index = self._get_index(self._last_driver_index)
                index = str(self._last_driver_index)
                self._last_driver_index += 1
        else:
            index = None
        image_bootindex = None
        image_boot = image_params.get("image_boot")
        if not re.search("boot=on\|off", self._qemu_help, re.MULTILINE):
            if image_boot in ["yes", "on", True]:
                image_bootindex = str(self.last_boot_index)
                self.last_boot_index += 1
            image_boot = "unused"
            image_bootindex = image_params.get("bootindex", image_bootindex)
        else:
            if image_boot in ["yes", "on", True]:
                if self.last_boot_index > 0:
                    image_boot = False
                self.last_boot_index += 1
        if "virtio" in image_params.get(
            "drive_format", ""
        ) or "virtio" in image_params.get("scsi_hba", ""):
            pci_bus = self._get_pci_bus(image_params, "disk", True)
        else:
            pci_bus = self._get_pci_bus(image_params, "disk", False)

        # data_root = data_dir.get_data_dir()
        # shared_dir = os.path.join(data_root, "shared")
        drive_format = image_params.get("drive_format")
        scsi_hba = image_params.get("scsi_hba", "virtio-scsi-pci")
        if drive_format == "virtio":  # translate virtio to ccw/device
            machine_type = image_params.get("machine_type")
            if "s390" in machine_type:  # s390
                drive_format = "virtio-blk-ccw"
            elif "mmio" in machine_type:  # mmio-based machine
                drive_format = "virtio-blk-device"
        if scsi_hba == "virtio-scsi-pci":
            if "mmio" in image_params.get("machine_type"):
                scsi_hba = "virtio-scsi-device"
            elif "s390" in image_params.get("machine_type"):
                scsi_hba = "virtio-scsi-ccw"
        # FIXME: skip this part
        # image_encryption = storage.ImageEncryption.encryption_define_by_params(
        #     image_name, image_params
        # )
        #
        # # all access information for the logical image
        # image_access = storage.ImageAccessInfo.access_info_define_by_params(
        #     image_name, image_params
        # )
        image_encryption = None
        image_access = None

        # image_base_dir = image_params.get("images_base_dir", data_root)
        # image_filename = storage.get_image_filename(image_params,
        #                                             image_base_dir)
        image_id = vt_imgr.query_image(image_name, self._name)
        image_uri = vt_imgr.get_image_info(image_id, f"spec.virt-images.{image_name}.spec.volume.spec.uri")
        image_filename = image_uri.get("uri")
        imgfmt = image_params.get("image_format")
        if (
                image_filename.startswith("vdpa://")
                and image_params.get("image_snapshot") == "yes"
        ):
            raise NotImplementedError(
                "vdpa does NOT support the snapshot!")
        # FIXME: skip this part
        # if Flags.BLOCKDEV in self.caps and image_params.get(
        #         "image_snapshot") == "yes":
        #     # FIXME: Most of attributes for the snapshot should be got from the
        #     #        base image's metadata, not from the Cartesian parameter,
        #     #        so we need to get the base image object, and then use it
        #     #        to create the snapshot.
        #     sn_params = Params()
        #     for k, v in image_params.items():
        #         sn_params["%s_%s" % (k, image_name)] = v
        #     sn = "vl_%s_%s" % (self.vmname, image_name)
        #     sn_params["image_chain"] = "%s %s" % (image_name, sn)
        #     sn_params["image_name"] = sn
        #     # Empty the image_size parameter so that qemu-img will align the
        #     # size of the snapshot to the base image
        #     sn_params["image_size"] = ""
        #     sn_img = qemu_storage.QemuImg(sn_params,
        #                                   data_dir.get_data_dir(), sn)
        #     image_filename = sn_img.create(sn_params)[0]
        #     os.chmod(image_filename, stat.S_IRUSR | stat.S_IWUSR)
        #     LOG.info(
        #         "'snapshot=on' is not supported by '-blockdev' but "
        #         "requested from the image '%s', imitating the behavior "
        #         "of '-drive' to keep compatibility",
        #         image_name,
        #     )
        #     self.temporary_image_snapshots.add(image_filename)
        #     image_encryption = storage.ImageEncryption.encryption_define_by_params(
        #         sn, sn_params
        #     )
        #     imgfmt = "qcow2"
        #
        # FIXME: skip this part
        # # external data file
        # ext_data_file = storage.QemuImg.external_data_file_defined_by_params(
        #     image_params, data_root, image_name
        # )
        #
        # slices_info = storage.ImageSlicesInfo.slices_info_define_by_params(
        #     image_name, image_params
        # )
        ext_data_file = None
        slices_info = None

        return __define_spec_by_variables(
            image_name,
            image_filename,
            pci_bus,
            index,
            drive_format,
            image_params.get("drive_cache"),
            image_params.get("drive_werror"),
            image_params.get("drive_rerror"),
            image_params.get("drive_serial"),
            image_params.get("image_snapshot"),
            image_boot,
            # storage.get_image_blkdebug_filename(image_params, shared_dir),
            None,
            image_params.get("drive_bus"),
            image_params.get("drive_unit"),
            image_params.get("drive_port"),
            image_bootindex,
            image_params.get("removable"),
            image_params.get("min_io_size"),
            image_params.get("opt_io_size"),
            image_params.get("physical_block_size"),
            image_params.get("logical_block_size"),
            image_params.get("image_readonly"),
            image_params.get("drive_scsiid"),
            image_params.get("drive_lun"),
            image_params.get("image_aio"),
            image_params.get("strict_mode") == "yes",
            media,
            imgfmt,
            image_params.get("drive_pci_addr"),
            scsi_hba,
            image_params.get("image_iothread"),
            image_params.get("blk_extra_params"),
            image_params.get("virtio-blk-pci_scsi"),
            image_params.get("drv_extra_params"),
            image_params.get("num_queues"),
            image_params.get("bus_extra_params"),
            image_params.get("force_drive_format"),
            image_encryption,
            image_access,
            ext_data_file,
            image_params.get("image_throttle_group"),
            image_params.get("image_auto_readonly"),
            image_params.get("image_discard"),
            image_params.get("image_copy_on_read"),
            image_params.get("image_iothread_vq_mapping"),
            slices_info,)

    def _parse_params(self):
        self._spec.update({"disks": [self._define_spec()]})


class QemuSpecDisks(QemuSpec):
    def __init__(self, name, vt_params, node):
        super(QemuSpecDisks, self).__init__(name, vt_params, node)
        self._parse_params()

    def _define_spec(self):
        for image_name in self._params.objects("images"):
            image_params = self._params.object_params(image_name)
            if image_params.get("boot_drive") == "no":
                continue
            self._specs.append(QemuSpecDisk(self._name, self._params,
                                            self._node.tag, image_name))

    def insert_spec(self, spec):
        if isinstance(spec, QemuSpecDisk):
            self._specs.append(spec)
            self._spec["disks"].append(spec.spec["disks"][0])
        else:
            raise InstanceSpecError("No support for the disk specification")

    def remove_spec(self, spec):
        self._specs.remove(spec)
        disks = self._spec["disks"]
        self._spec["disks"].remove(spec.spec["disks"][0]) # FIXME: get the disk spec by index 0

    def _parse_params(self):
        self._define_spec()
        self._spec.update({"disks": [disk.spec["disks"][0] for disk in self._specs]})
