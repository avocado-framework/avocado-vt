"""
tpm device support class(es)

http://libvirt.org/formatdomain.html#elementsTpm
"""

import logging

from virttest import xml_utils
from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base

LOG = logging.getLogger("avocado." + __name__)


class Tpm(base.UntypedDeviceBase):

    __slots__ = ("tpm_model", "backend")

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute(
            "tpm_model", self, parent_xpath="/", tag_name="tpm", attribute="model"
        )
        accessors.XMLElementNest(
            "backend",
            self,
            parent_xpath="/",
            tag_name="backend",
            subclass=self.Backend,
            subclass_dargs={"virsh_instance": virsh_instance},
        )
        super(Tpm, self).__init__(device_tag="tpm", virsh_instance=virsh_instance)

    class Backend(base.base.LibvirtXMLBase):
        """
        Tpm backend xml class.

        Properties:

        type:
            string. backend type
        version:
            string. backend version
        debug:
            string. backend debug
        persistent_state:
            string. backend persistent_state
        path:
            string. device path
        secret:
            string. encryption secret
        active_pcr_banks:
            string.  backend active_pcr_banks
        source:
            string.  backend source
        """

        __slots__ = (
            "backend_type",
            "backend_version",
            "backend_debug",
            "persistent_state",
            "device_path",
            "encryption_secret",
            "active_pcr_banks",
            "source",
        )

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLAttribute(
                property_name="backend_type",
                libvirtxml=self,
                parent_xpath="/",
                tag_name="backend",
                attribute="type",
            )
            accessors.XMLAttribute(
                property_name="backend_version",
                libvirtxml=self,
                parent_xpath="/",
                tag_name="backend",
                attribute="version",
            )
            accessors.XMLAttribute(
                property_name="backend_debug",
                libvirtxml=self,
                parent_xpath="/",
                tag_name="backend",
                attribute="debug",
            )
            accessors.XMLAttribute(
                property_name="persistent_state",
                libvirtxml=self,
                parent_xpath="/",
                tag_name="backend",
                attribute="persistent_state",
            )
            accessors.XMLAttribute(
                property_name="device_path",
                libvirtxml=self,
                parent_xpath="/",
                tag_name="device",
                attribute="path",
            )
            accessors.XMLAttribute(
                property_name="encryption_secret",
                libvirtxml=self,
                parent_xpath="/",
                tag_name="encryption",
                attribute="secret",
            )
            accessors.XMLElementNest(
                "active_pcr_banks",
                libvirtxml=self,
                parent_xpath="/",
                tag_name="active_pcr_banks",
                subclass=self.ActivePCRBanks,
                subclass_dargs={"virsh_instance": virsh_instance},
            )
            accessors.XMLElementDict(
                property_name="source",
                libvirtxml=self,
                parent_xpath="/",
                tag_name="source",
            )
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = "<backend/>"

        class ActivePCRBanks(base.base.LibvirtXMLBase):
            """
            Tpm active_pcr_banks xml class.

            Elements:
            sha1: supported element sha1
            sha256: supported element sha256
            sha384: supported element sha384
            sha512: supported element sha512
            pcrbank_list: list of any customized elements. It does not support setup_attrs().
            """

            __slots__ = ("sha1", "sha256", "sha384", "sha512", "pcrbank_list")

            def __init__(self, virsh_instance=base.base.virsh):
                for slot in ("sha1", "sha256", "sha384", "sha512"):
                    accessors.XMLElementBool(
                        slot, self, parent_xpath="/", tag_name=slot
                    )
                accessors.AllForbidden(property_name="pcrbank_list", libvirtxml=self)
                super(self.__class__, self).__init__(virsh_instance=virsh_instance)
                self.xml = "<active_pcr_banks/>"

            def get_pcrbank_list(self):
                """
                Return all active_pcr_banks in xml
                """
                pcrbank_list = []
                root = self.__dict_get__("xml").getroot()
                for pcrbank in root:
                    pcrbank_list.append(pcrbank.tag)
                return pcrbank_list

            def has_pcrbank(self, name):
                """
                Return true if the given active_pcr_banks exist in xml
                """
                return name in self.get_pcrbank_list()

            def add_pcrbank(self, name):
                """
                Add a active_pcr_banks element to xml

                :params name: active_pcr_banks name
                """
                if self.has_pcrbank(name):
                    LOG.debug("PCR bank %s already exist, so remove it", name)
                    self.remove_pcrbank(name)
                root = self.__dict_get__("xml").getroot()
                xml_utils.ElementTree.SubElement(root, name)

            def remove_pcrbank(self, name):
                """
                Remove a active_pcr_banks element from xml

                :params name: active_pcr_banks name
                """
                root = self.__dict_get__("xml").getroot()
                remove_pcrbank = root.find(name)
                if remove_pcrbank is None:
                    LOG.error("PCR bank %s doesn't exist", name)
                else:
                    root.remove(remove_pcrbank)
