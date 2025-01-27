"""
Module simplifying manipulation of XML described at
http://libvirt.org/formatbackup.html
"""

from virttest.libvirt_xml import accessors, base, xcepts


class BackupXML(base.LibvirtXMLBase):
    """
    Domain backup XML class. Following are 2 samples for push mode backup xml
    and pull mode backup xml.
    Push mode:
    <domainbackup mode="push">
      <incremental>checkpoint_0</incremental>
        <disks>
            <disk name='vda' backup='no'/>
            <disk name='vdb' type='file'>
                <driver type='qcow2'/>
                <target file='/tmp/push_inc_backup.img'>
                    <encryption format='luks'>
                        <secret type='passphrase' usage='/luks/img'/>
                    </encryption>
                </target>
            </disk>
        </disks>
    </domainbackup>
    Pull mode:
    <domainbackup mode='pull'>
        <incremental>checkpoint_0</incremental>
        <server transport='tcp' name='localhost' port='10809' tls="yes"/>
        <disks>
            <disk name='vda' backup='no'/>
            <disk name='vdb' backup='yes' type='file'>
                <driver type='qcow2'/>
                <scratch file='/tmp/scratch_file'>
                    <encryption format='luks'>
                        <secret type='passphrase' usage='/luks/img'/>
                    </encryption>
                </scratch>
            </disk>
        </disks>
    </domainbackup>

    Properties:
        mode:
            string (push/pull), backup mode
        incremental:
            string, incremental backup based on which checkpoint
        server:
            dict, keys: transport, socket, name, port
    """

    __slots__ = ("mode", "incremental", "server", "disks")

    __uncompareable__ = base.LibvirtXMLBase.__uncompareable__

    __schema_name__ = "domainbackup"

    def __init__(self, virsh_instance=base.virsh):
        accessors.XMLAttribute(
            "mode", self, parent_xpath="/", tag_name="domainbackup", attribute="mode"
        )
        accessors.XMLElementText(
            "incremental", self, parent_xpath="/", tag_name="incremental"
        )
        accessors.XMLElementDict("server", self, parent_xpath="/", tag_name="server")
        accessors.XMLElementList(
            "disks",
            self,
            parent_xpath="/disks",
            marshal_from=self.marshal_from_disks,
            marshal_to=self.marshal_to_disks,
            has_subclass=True,
        )
        super(self.__class__, self).__init__(virsh_instance=virsh_instance)
        self.xml = "<domainbackup/>"

    @staticmethod
    def marshal_from_disks(item, index, libvirtxml):
        """
        Convert an xml object to disk tag and xml element.
        """
        if isinstance(item, BackupXML.DiskXML):
            return "disk", item
        elif isinstance(item, dict):
            disk = BackupXML.DiskXML()
            disk.setup_attrs(**item)
            return "disk", disk
        else:
            raise xcepts.LibvirtXMLError(
                "Expected a list of DiskXML " "instances, not a %s" % str(item)
            )

    @staticmethod
    def marshal_to_disks(tag, new_treefile, index, libvirtxml):
        """
        Convert a disk tag xml element to an object of DiskXML.
        """
        if tag != "disk":
            return None
        newone = BackupXML.DiskXML(virsh_instance=libvirtxml.virsh)
        newone.xmltreefile = new_treefile
        return newone

    class DiskXML(base.LibvirtXMLBase):
        """
        Disk XML class, used to set disk specific parameters when do backup

        Properties:
            name:
                string, disk name
            backup:
                string (yes/no), whether do backup for this disk
            exportname:
                string, export name of NBD, only valid for pull-mode backup
            exportbitmap:
                string, export bitmap name, only valid for pull-mode backup
            type:
                string (file/block/network), describe the type of the disk,
                'network' is not valid for now due to bz:
                https://bugzilla.redhat.com/show_bug.cgi?id=1812100
            backupmode:
                string, indicate if the disk will do full or incremental backup
            incremental:
                string, indicate the incremental backup is from which checkpoint
            target:
                libvirt_xml.backup_xml.DiskXML.DiskTarget instance
            driver:
                dict, keys: type. Value of type could be qcow2/raw or
                other format
            scratch:
                libvirt_xml.backup_xml.DiskXML.DiskScratch instance
        """

        __slots__ = (
            "name",
            "backup",
            "exportname",
            "exportbitmap",
            "type",
            "backupmode",
            "incremental",
            "target",
            "driver",
            "scratch",
        )

        def __init__(self, virsh_instance=base.virsh):
            accessors.XMLAttribute(
                "name", self, parent_xpath="/", tag_name="disk", attribute="name"
            )
            accessors.XMLAttribute(
                "backup", self, parent_xpath="/", tag_name="disk", attribute="backup"
            )
            accessors.XMLAttribute(
                "exportname",
                self,
                parent_xpath="/",
                tag_name="disk",
                attribute="exportname",
            )
            accessors.XMLAttribute(
                "exportbitmap",
                self,
                parent_xpath="/",
                tag_name="disk",
                attribute="exportbitmap",
            )
            accessors.XMLAttribute(
                "type", self, parent_xpath="/", tag_name="disk", attribute="type"
            )
            accessors.XMLAttribute(
                "backupmode",
                self,
                parent_xpath="/",
                tag_name="disk",
                attribute="backupmode",
            )
            accessors.XMLAttribute(
                "incremental",
                self,
                parent_xpath="/",
                tag_name="disk",
                attribute="incremental",
            )
            accessors.XMLElementNest(
                "target",
                self,
                parent_xpath="/",
                tag_name="target",
                subclass=self.DiskTarget,
                subclass_dargs={"virsh_instance": virsh_instance},
            )
            accessors.XMLElementDict(
                "driver", self, parent_xpath="/", tag_name="driver"
            )
            accessors.XMLElementNest(
                "scratch",
                self,
                parent_xpath="/",
                tag_name="scratch",
                subclass=self.DiskScratch,
                subclass_dargs={"virsh_instance": virsh_instance},
            )

            super(self.__class__, self).__init__(virsh_instance=virsh_instance)
            self.xml = "<disk/>"

        class DiskTarget(base.LibvirtXMLBase):
            """
            Backup disk target XML class

            Properties:

            attrs: Dictionary of attributes
            encryption: libvirt_xml.backup_xml.Disk.DiskTarget.Encryption instances
            """

            __slots__ = ("attrs", "encryption")

            def __init__(self, virsh_instance=base.virsh):
                accessors.XMLElementDict(
                    "attrs", self, parent_xpath="/", tag_name="target"
                )
                accessors.XMLElementNest(
                    "encryption",
                    self,
                    parent_xpath="/",
                    tag_name="encryption",
                    subclass=self.Encryption,
                    subclass_dargs={"virsh_instance": virsh_instance},
                )
                super(self.__class__, self).__init__(virsh_instance=virsh_instance)
                self.xml = "<target/>"

            def new_encryption(self, **dargs):
                """
                Return a new encryption instance and set properties from dargs
                """
                new_one = self.Encryption(virsh_instance=self.virsh)
                for key, value in list(dargs.items()):
                    setattr(new_one, key, value)
                return new_one

            class Encryption(base.LibvirtXMLBase):
                """
                Backup disk encryption XML class

                Properties:
                    encryption:
                        string.
                    secret:
                        dict, keys: type, usage, uuid
                """

                __slots__ = ("encryption", "secret")

                def __init__(self, virsh_instance=base.virsh):
                    accessors.XMLAttribute(
                        "encryption",
                        self,
                        parent_xpath="/",
                        tag_name="encryption",
                        attribute="format",
                    )
                    accessors.XMLElementDict(
                        "secret", self, parent_xpath="/", tag_name="secret"
                    )
                    super(self.__class__, self).__init__(virsh_instance=virsh_instance)
                    self.xml = "<encryption/>"

        class DiskScratch(DiskTarget):
            """
            Backup disk scratch XML class, this is only used in pull-mode
            backup, and its structure is samilar as DiskTarget class

            Properties:

            attrs: Dictionary of attributes
            encryption: libvirt_xml.backup_xml.Disk.DiskTarget.Encryption instances
            """

            __slots__ = ("attrs", "encryption")

            def __init__(self, virsh_instance=base.virsh):
                accessors.XMLElementDict(
                    "attrs", self, parent_xpath="/", tag_name="scratch"
                )
                accessors.XMLElementNest(
                    "encryption",
                    self,
                    parent_xpath="/",
                    tag_name="encryption",
                    subclass=self.Encryption,
                    subclass_dargs={"virsh_instance": virsh_instance},
                )
                base.LibvirtXMLBase.__init__(self, virsh_instance=virsh_instance)
                self.xml = "<scratch/>"
