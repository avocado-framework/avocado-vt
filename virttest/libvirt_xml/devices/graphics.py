"""
graphics framebuffer device support class(es)

http://libvirt.org/formatdomain.html#elementsGraphics
"""

from virttest.libvirt_xml import accessors, vm_xml, xcepts
from virttest.libvirt_xml.devices import base


class Graphics(base.TypedDeviceBase):

    __slots__ = (
        "passwd",
        "channels",
        "listen",
        "autoport",
        "port",
        "tlsPort",
        "defaultMode",
        "image_compression",
        "jpeg_compression",
        "zlib_compression",
        "playback_compression",
        "listen_attrs",
        "passwdValidTo",
        "clipboard_copypaste",
        "filetransfer_enable",
        "streaming_mode",
    )

    def __init__(self, type_name="vnc", virsh_instance=base.base.virsh):
        # Add additional attribute 'passwd' for security
        accessors.XMLAttribute(
            "passwd", self, parent_xpath="/", tag_name="graphics", attribute="passwd"
        )
        accessors.XMLAttribute(
            "passwdValidTo",
            self,
            parent_xpath="/",
            tag_name="graphics",
            attribute="passwdValidTo",
        )
        accessors.XMLAttribute(
            "listen", self, parent_xpath="/", tag_name="graphics", attribute="listen"
        )
        accessors.XMLAttribute(
            "autoport",
            self,
            parent_xpath="/",
            tag_name="graphics",
            attribute="autoport",
        )
        accessors.XMLAttribute(
            "port", self, parent_xpath="/", tag_name="graphics", attribute="port"
        )
        accessors.XMLAttribute(
            "tlsPort", self, parent_xpath="/", tag_name="graphics", attribute="tlsPort"
        )
        accessors.XMLAttribute(
            "type", self, parent_xpath="/", tag_name="graphics", attribute="type"
        )
        accessors.XMLAttribute(
            "defaultMode",
            self,
            parent_xpath="/",
            tag_name="graphics",
            attribute="defaultMode",
        )
        accessors.XMLAttribute(
            "image_compression",
            self,
            parent_xpath="/",
            tag_name="image",
            attribute="compression",
        )
        accessors.XMLAttribute(
            "jpeg_compression",
            self,
            parent_xpath="/",
            tag_name="jpeg",
            attribute="compression",
        )
        accessors.XMLAttribute(
            "zlib_compression",
            self,
            parent_xpath="/",
            tag_name="zlib",
            attribute="compression",
        )
        accessors.XMLAttribute(
            "playback_compression",
            self,
            parent_xpath="/",
            tag_name="playback",
            attribute="compression",
        )
        accessors.XMLAttribute(
            "clipboard_copypaste",
            self,
            parent_xpath="/",
            tag_name="clipboard",
            attribute="copypaste",
        )
        accessors.XMLAttribute(
            "filetransfer_enable",
            self,
            parent_xpath="/",
            tag_name="filetransfer",
            attribute="enable",
        )
        accessors.XMLAttribute(
            "streaming_mode",
            self,
            parent_xpath="/",
            tag_name="streaming",
            attribute="mode",
        )
        accessors.XMLElementDict(
            "listen_attrs", self, parent_xpath="/", tag_name="listen"
        )
        accessors.XMLElementList(
            "channels",
            self,
            parent_xpath="/",
            marshal_from=self.marshal_from_channels,
            marshal_to=self.marshal_to_channels,
        )
        super(Graphics, self).__init__(
            device_tag="graphics", type_name=type_name, virsh_instance=virsh_instance
        )

    @staticmethod
    def marshal_from_channels(item, index, libvirtxml):
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError(
                "Expected a dictionary of channel " "attributes, not a %s" % str(item)
            )
        return "channel", dict(item)

    @staticmethod
    def marshal_to_channels(tag, attr_dict, index, libvirtxml):
        if tag != "channel":
            return None
        return dict(attr_dict)

    def add_channel(self, **attributes):
        """
        Convenience method for appending channel from dictionary of attributes
        """
        channels = self.channels
        channels.append(attributes)
        self.channels = channels

    @staticmethod
    def change_graphic_type_passwd(vm_name, graphic, passwd=None):
        """
        Change the graphic type name and passwd

        :param vm_name: name of vm
        :param graphic: graphic type, spice or vnc
        :param passwd: password for graphic
        """
        vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
        devices = vmxml.devices
        graphics = devices.by_device_tag("graphics")[0]
        graphics.type_name = graphic
        if passwd is not None:
            graphics.passwd = passwd
        vmxml.devices = devices
        vmxml.sync()

    @staticmethod
    def add_graphic(vm_name, passwd=None, graphic="vnc", add_channel=False):
        """
        Add spice ssl or vnc graphic with passwd

        :param vm_name: name of vm
        :param passwd: password for graphic
        :param graphic: graphic type, spice or vnc
        :param add_channel: add channel for spice
        """
        vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
        grap = vmxml.get_device_class("graphics")(type_name=graphic)
        if passwd is not None:
            grap.passwd = passwd
        grap.autoport = "yes"
        if graphic == "spice" and add_channel:
            grap.add_channel(name="main", mode="secure")
            grap.add_channel(name="inputs", mode="secure")
        vmxml.devices = vmxml.devices.append(grap)
        vmxml.sync()

    @staticmethod
    def del_graphic(vm_name):
        """
        Del original graphic device

        :param vm_name: name of vm
        """
        vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
        vmxml.xmltreefile.remove_by_xpath("/devices/graphics", remove_all=True)
        vmxml.xmltreefile.write()
        vmxml.sync()
