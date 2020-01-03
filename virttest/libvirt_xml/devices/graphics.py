"""
graphics framebuffer device support class(es)

http://libvirt.org/formatdomain.html#elementsGraphics
"""

from virttest.libvirt_xml import accessors, vm_xml
from virttest.libvirt_xml.devices import base


class Graphics(base.TypedDeviceBase):

    __slots__ = ('passwd', 'channel', 'listen', 'listens', 'autoport', 'port',
                 'tlsPort', 'defaultMode', 'image_compression',
                 'jpeg_compression', 'zlib_compression', 'playback_compression',
                 'listen_type', 'listen_addr', 'passwdValidTo', 'clipboard_copypaste',
                 'filetransfer_enable', 'streaming_mode')

    def __init__(self, type_name='vnc', virsh_instance=base.base.virsh):
        # Add additional attribute 'passwd' for security
        accessors.XMLAttribute('passwd', self, parent_xpath='/',
                               tag_name='graphics', attribute='passwd')
        accessors.XMLAttribute('passwdValidTo', self, parent_xpath='/',
                               tag_name='graphics', attribute='passwdValidTo')
        accessors.XMLAttribute('listen', self, parent_xpath='/',
                               tag_name='graphics', attribute='listen')
        accessors.XMLAttribute('autoport', self, parent_xpath='/',
                               tag_name='graphics', attribute='autoport')
        accessors.XMLAttribute('port', self, parent_xpath='/',
                               tag_name='graphics', attribute='port')
        accessors.XMLAttribute('tlsPort', self, parent_xpath='/',
                               tag_name='graphics', attribute='tlsPort')
        accessors.XMLAttribute('type', self, parent_xpath='/',
                               tag_name='graphics', attribute='type')
        accessors.XMLAttribute('defaultMode', self, parent_xpath='/',
                               tag_name='graphics', attribute='defaultMode')
        accessors.XMLAttribute('image_compression', self, parent_xpath='/',
                               tag_name='image', attribute='compression')
        accessors.XMLAttribute('jpeg_compression', self, parent_xpath='/',
                               tag_name='jpeg', attribute='compression')
        accessors.XMLAttribute('zlib_compression', self, parent_xpath='/',
                               tag_name='zlib', attribute='compression')
        accessors.XMLAttribute('playback_compression', self, parent_xpath='/',
                               tag_name='playback', attribute='compression')
        accessors.XMLAttribute('listen_type', self, parent_xpath='/',
                               tag_name='listen', attribute='type')
        accessors.XMLAttribute('listen_addr', self, parent_xpath='/',
                               tag_name='listen', attribute='address')
        accessors.XMLAttribute('clipboard_copypaste', self, parent_xpath='/',
                               tag_name='clipboard', attribute='copypaste')
        accessors.XMLAttribute('filetransfer_enable', self, parent_xpath='/',
                               tag_name='filetransfer', attribute='enable')
        accessors.XMLAttribute('streaming_mode', self, parent_xpath='/',
                               tag_name='streaming', attribute='mode')
        super(Graphics, self).__init__(device_tag='graphics',
                                       type_name=type_name,
                                       virsh_instance=virsh_instance)

    def get_channel(self):
        """
        Return a list of dictionaries containing each channel's attributes
        """
        return self._get_list('channel')

    def set_channel(self, value):
        """
        Set all channel to the value list of dictionaries of channel attributes
        """
        self._set_list('channel', value)

    def del_channel(self):
        """
        Remove the list of dictionaries containing each channel's attributes
        """
        self._del_list('channel')

    def add_channel(self, **attributes):
        """
        Convenience method for appending channel from dictionary of attributes
        """
        self._add_item('channel', **attributes)

    def get_listens(self):
        """
        Return a list of dictionaries containing each listen's attributes
        """
        return self._get_list('listen')

    def set_listens(self, value):
        """
        Set all listens to the value list of dictionaries of listen attributes
        """
        self._set_list('listen', value)

    def del_listens(self):
        """
        Remove the list of dictionaries containing each listen's attributes
        """
        self._del_list('listen')

    def add_listens(self, **attributes):
        """
        Convenience method for appending listens from dictionary of attributes
        """
        self._add_item('listen', **attributes)

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
        graphics = devices.by_device_tag('graphics')[0]
        graphics.type_name = graphic
        if passwd is not None:
            graphics.passwd = passwd
        vmxml.devices = devices
        vmxml.sync()

    @staticmethod
    def add_graphic(vm_name, passwd=None, graphic="vnc",
                    add_channel=False):
        """
        Add spice ssl or vnc graphic with passwd

        :param vm_name: name of vm
        :param passwd: password for graphic
        :param graphic: graphic type, spice or vnc
        :param add_channel: add channel for spice
        """
        vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
        grap = vmxml.get_device_class('graphics')(type_name=graphic)
        if passwd is not None:
            grap.passwd = passwd
        grap.autoport = "yes"
        if graphic == "spice" and add_channel:
            grap.add_channel(name='main', mode='secure')
            grap.add_channel(name='inputs', mode='secure')
        vmxml.devices = vmxml.devices.append(grap)
        vmxml.sync()

    @staticmethod
    def del_graphic(vm_name):
        """
        Del original graphic device

        :param vm_name: name of vm
        """
        vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
        vmxml.xmltreefile.remove_by_xpath('/devices/graphics', remove_all=True)
        vmxml.xmltreefile.write()
        vmxml.sync()
