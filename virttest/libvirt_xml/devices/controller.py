"""
controller device support class(es)

http://libvirt.org/formatdomain.html#elementsControllers
"""

from virttest.libvirt_xml import accessors, xcepts
from virttest.libvirt_xml.devices import base, librarian


class Controller(base.TypedDeviceBase):

    __slots__ = (
        "type",
        "index",
        "model",
        "ports",
        "vectors",
        "driver",
        "driver_iothreads",
        "address",
        "pcihole64",
        "target",
        "alias",
        "model_name",
        "node",
    )

    def __init__(self, type_name="pci", virsh_instance=base.base.virsh):
        super(Controller, self).__init__(
            device_tag="controller", type_name=type_name, virsh_instance=virsh_instance
        )
        # TODO: Remove 'type' since it's duplicated with 'type_name'
        accessors.XMLAttribute(
            "type", self, parent_xpath="/", tag_name="controller", attribute="type"
        )
        accessors.XMLAttribute(
            "index", self, parent_xpath="/", tag_name="controller", attribute="index"
        )
        accessors.XMLAttribute(
            "model", self, parent_xpath="/", tag_name="controller", attribute="model"
        )
        accessors.XMLAttribute(
            "ports", self, parent_xpath="/", tag_name="controller", attribute="ports"
        )
        accessors.XMLAttribute(
            "vectors",
            self,
            parent_xpath="/",
            tag_name="controller",
            attribute="vectors",
        )
        accessors.XMLElementText(
            "pcihole64", self, parent_xpath="/", tag_name="pcihole64"
        )
        accessors.XMLElementDict("driver", self, parent_xpath="/", tag_name="driver")
        accessors.XMLElementNest(
            "driver_iothreads",
            self,
            parent_xpath="/driver",
            tag_name="iothreads",
            subclass=self.ControllerDriverIOthreadsXML,
            subclass_dargs={"virsh_instance": virsh_instance},
        )
        accessors.XMLElementNest(
            "address",
            self,
            parent_xpath="/",
            tag_name="address",
            subclass=self.Address,
            subclass_dargs={"type_name": "pci", "virsh_instance": virsh_instance},
        )
        accessors.XMLElementDict("target", self, parent_xpath="/", tag_name="target")
        accessors.XMLElementText("node", self, parent_xpath="/target", tag_name="node")
        accessors.XMLElementDict("alias", self, parent_xpath="/", tag_name="alias")
        accessors.XMLElementDict("model_name", self, parent_xpath="/", tag_name="model")

    Address = librarian.get("address")

    def new_controller_address(self, **dargs):
        """
        Return a new controller Address instance and set properties from dargs
        """
        new_one = self.Address("pci", virsh_instance=self.virsh)
        for key, value in list(dargs.items()):
            setattr(new_one, key, value)
        return new_one

    class ControllerDriverIOthreadsXML(base.base.LibvirtXMLBase):
        """
        iothreads tag XML class

        Elements:
            iothread
        """

        __slots__ = ("iothread",)

        def __init__(self, virsh_instance=base.base.virsh):
            accessors.XMLElementList(
                "iothread",
                self,
                forbidden=[],
                parent_xpath="/",
                marshal_from=self.marshal_from_iothread,
                marshal_to=self.marshal_to_iothread,
                has_subclass=True,
            )
            super(Controller.ControllerDriverIOthreadsXML, self).__init__(
                virsh_instance=virsh_instance
            )
            self.xml = "<iothreads/>"

        @staticmethod
        def marshal_from_iothread(item, index, libvirtxml):
            """
            Convert an xml object to iothread tag and xml element.
            """
            if isinstance(item, Controller.ControllerDriverIOthreadsXML.IOthreadXML):
                return "iothread", item
            elif isinstance(item, dict):
                iothread = Controller.ControllerDriverIOthreadsXML.IOthreadXML()
                iothread.setup_attrs(**item)
                return "iothread", iothread
            else:
                raise xcepts.LibvirtXMLError(
                    "Expected a list of iothread instances, not a %s" % str(item)
                )

        @staticmethod
        def marshal_to_iothread(tag, new_treefile, index, libvirtxml):
            """
            Convert an iothread tag xml element to an object of VMIothreadXML.
            """
            if tag != "iothread":
                return None  # Don't convert this item
            newone = Controller.ControllerDriverIOthreadsXML.IOthreadXML(
                virsh_instance=libvirtxml.virsh
            )
            newone.xmltreefile = new_treefile
            return newone

        class IOthreadXML(base.base.LibvirtXMLBase):
            """
            Class of controller driver iothread tag
            """

            __slots__ = ("id", "queue")

            def __init__(self, virsh_instance=base.base.virsh):
                accessors.XMLAttribute(
                    property_name="id",
                    libvirtxml=self,
                    forbidden=[],
                    parent_xpath="/",
                    tag_name="iothread",
                    attribute="id",
                )
                accessors.XMLElementList(
                    "queue",
                    self,
                    parent_xpath="/",
                    marshal_from=self.marshal_from_queue,
                    marshal_to=self.marshal_to_queue,
                )
                super(
                    Controller.ControllerDriverIOthreadsXML.IOthreadXML, self
                ).__init__(virsh_instance=virsh_instance)
                self.xml = "<iothread/>"

            @staticmethod
            def marshal_from_queue(item, index, libvirtxml):
                """
                Convert a dict to queue tag and attributes
                """
                del index
                del libvirtxml
                if not isinstance(item, dict):
                    raise xcepts.LibvirtXMLError(
                        "Expected a dictionary of queue "
                        "attributes, not a %s" % str(item)
                    )
                return ("queue", dict(item))

            @staticmethod
            def marshal_to_queue(tag, attr_dict, index, libvirtxml):
                """
                Convert a queue tag and attributes to a dict
                """
                del index
                del libvirtxml
                if tag != "queue":
                    return None
                return dict(attr_dict)
