"""
memory device support class(es)

"""

from virttest.libvirt_xml import accessors
from virttest.libvirt_xml.devices import base, librarian


class Memory(base.UntypedDeviceBase):

    __slots__ = (
        "mem_model",
        "target",
        "source",
        "address",
        "mem_discard",
        "mem_access",
        "alias",
        "uuid",
    )

    def __init__(self, virsh_instance=base.base.virsh):
        accessors.XMLAttribute(
            "mem_model", self, parent_xpath="/", tag_name="memory", attribute="model"
        )
        accessors.XMLAttribute(
            "mem_discard",
            self,
            parent_xpath="/",
            tag_name="memory",
            attribute="discard",
        )
        accessors.XMLAttribute(
            "mem_access", self, parent_xpath="/", tag_name="memory", attribute="access"
        )
        accessors.XMLElementText("uuid", self, parent_xpath="/", tag_name="uuid")
        accessors.XMLElementNest(
            "target",
            self,
            parent_xpath="/",
            tag_name="target",
            subclass=self.Target,
            subclass_dargs={"virsh_instance": virsh_instance},
        )
        accessors.XMLElementNest(
            "source",
            self,
            parent_xpath="/",
            tag_name="source",
            subclass=self.Source,
            subclass_dargs={"virsh_instance": virsh_instance},
        )
        accessors.XMLElementNest(
            "address",
            self,
            parent_xpath="/",
            tag_name="address",
            subclass=self.Address,
            subclass_dargs={"type_name": "dimm", "virsh_instance": virsh_instance},
        )
        accessors.XMLElementDict("alias", self, parent_xpath="/", tag_name="alias")
        super(Memory, self).__init__(device_tag="memory", virsh_instance=virsh_instance)
        self.xml = "<memory/>"

    Address = librarian.get("address")

    class Target(base.base.LibvirtXMLBase):
        """
        Memory target xml class.

        Properties:

        size, node, requested_size, current_size, block_size:
            int.
        size_unit, requested_unit, current_unit, block_unit:
            string.
        """

        __slots__ = (
            "size",
            "size_unit",
            "node",
            "label",
            "requested_size",
            "requested_unit",
            "current_size",
            "current_unit",
            "block_size",
            "block_unit",
            "readonly",
            "address",
            "attrs",
        )

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLElementInt("size", self, parent_xpath="/", tag_name="size")
            accessors.XMLAttribute(
                property_name="size_unit",
                libvirtxml=self,
                forbidden=None,
                parent_xpath="/",
                tag_name="size",
                attribute="unit",
            )
            accessors.XMLElementInt(
                "requested_size", self, parent_xpath="/", tag_name="requested"
            )
            accessors.XMLAttribute(
                property_name="requested_unit",
                libvirtxml=self,
                forbidden=None,
                parent_xpath="/",
                tag_name="requested",
                attribute="unit",
            )
            accessors.XMLElementInt(
                "current_size", self, parent_xpath="/", tag_name="current"
            )
            accessors.XMLAttribute(
                property_name="current_unit",
                libvirtxml=self,
                forbidden=None,
                parent_xpath="/",
                tag_name="current",
                attribute="unit",
            )
            accessors.XMLElementInt(
                "block_size", self, parent_xpath="/", tag_name="block"
            )
            accessors.XMLAttribute(
                property_name="block_unit",
                libvirtxml=self,
                forbidden=None,
                parent_xpath="/",
                tag_name="block",
                attribute="unit",
            )
            accessors.XMLElementInt("node", self, parent_xpath="/", tag_name="node")
            accessors.XMLElementNest(
                "label",
                self,
                parent_xpath="/",
                tag_name="label",
                subclass=self.Label,
                subclass_dargs={"virsh_instance": virsh_instance},
            )
            accessors.XMLElementBool(
                "readonly", self, parent_xpath="/", tag_name="readonly"
            )
            accessors.XMLElementNest(
                "address",
                self,
                parent_xpath="/",
                tag_name="address",
                subclass=Memory.Address,
                subclass_dargs={"type_name": "pci", "virsh_instance": virsh_instance},
            )
            accessors.XMLElementDict("attrs", self, parent_xpath="/", tag_name="target")
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = "<target/>"

        class Label(base.base.LibvirtXMLBase):
            """
            Memory target label xml class.

            Properties:

            size:
                int.
            size_unit:
                string.
            """

            __slots__ = ("size", "size_unit")

            def __init__(self, virsh_instance=base.base.virsh):
                accessors.XMLElementInt("size", self, parent_xpath="/", tag_name="size")
                accessors.XMLAttribute(
                    property_name="size_unit",
                    libvirtxml=self,
                    forbidden=None,
                    parent_xpath="/",
                    tag_name="size",
                    attribute="unit",
                )
                super(self.__class__, self).__init__(virsh_instance=virsh_instance)
                self.xml = "<label/>"

    class Source(base.base.LibvirtXMLBase):
        """
        Memory source xml class.

        Properties:

        pagesize: int, override the default host page size used for backing the memory device
        pagesize_unit: str, the unit of pagesize
        nodemask: str, override the default set of NUMA nodes where the memory would be allocated
        path: str, the path in the host that backs the memory device in the guest
        alignsize: int, the page size alignment used to mmap the address range for the backend path
        alignsize_unit: str, the unit of alignsize
        pmem:boolean, persistent memory feature is enabled
        """

        __slots__ = (
            "pagesize",
            "pagesize_unit",
            "nodemask",
            "path",
            "alignsize",
            "alignsize_unit",
            "pmem",
        )

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLElementInt(
                "pagesize", self, parent_xpath="/", tag_name="pagesize"
            )
            accessors.XMLAttribute(
                property_name="pagesize_unit",
                libvirtxml=self,
                forbidden=None,
                parent_xpath="/",
                tag_name="pagesize",
                attribute="unit",
            )
            accessors.XMLElementText(
                "nodemask", self, parent_xpath="/", tag_name="nodemask"
            )
            accessors.XMLElementText("path", self, parent_xpath="/", tag_name="path")
            accessors.XMLElementInt(
                "alignsize", self, parent_xpath="/", tag_name="alignsize"
            )
            accessors.XMLAttribute(
                property_name="alignsize_unit",
                libvirtxml=self,
                forbidden=None,
                parent_xpath="/",
                tag_name="alignsize",
                attribute="unit",
            )
            accessors.XMLElementBool("pmem", self, parent_xpath="/", tag_name="pmem")
            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = "<source/>"

    def new_mem_address(self, type_name="dimm", **dargs):
        """
        Return a new disk Address instance and set properties from dargs
        """
        new_one = self.Address(type_name=type_name, virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one
