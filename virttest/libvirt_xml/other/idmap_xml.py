# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
#   Copyright Red Hat
#
#   SPDX-License-Identifier: GPL-2.0
#
#   Author: smitterl@redhat.com
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
from virttest import virsh
from virttest.libvirt_xml import accessors, base, xcepts


class VMIDMapXML(base.LibvirtXMLBase):
    """
    idmap xml class of vmxml

    Example:
      <idmap>
        <uid start='0' target='1000' count='10'/>
        <gid start='0' target='1000' count='10'/>
      </idmap>
    """

    __slots__ = ("uid", "gid", "uids", "gids")

    def __init__(self, virsh_instance=virsh):
        accessors.XMLElementDict(
            property_name="uid",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="uid",
        )
        accessors.XMLElementDict(
            property_name="gid",
            libvirtxml=self,
            forbidden=None,
            parent_xpath="/",
            tag_name="gid",
        )
        accessors.XMLElementList(
            property_name="uids",
            libvirtxml=self,
            parent_xpath="/",
            marshal_from=self.marshal_from_uids,
            marshal_to=self.marshal_to_uids,
            has_subclass=False,
        )
        accessors.XMLElementList(
            property_name="gids",
            libvirtxml=self,
            parent_xpath="/",
            marshal_from=self.marshal_from_gids,
            marshal_to=self.marshal_to_gids,
            has_subclass=False,
        )
        super(VMIDMapXML, self).__init__(virsh_instance=virsh_instance)
        self.xml = "<idmap/>"

    @staticmethod
    def _marshal_from_ids(item, index, libvirtxml, tag):
        """Convert dictionary to xml object"""
        del index
        del libvirtxml
        if not isinstance(item, dict):
            raise xcepts.LibvirtXMLError(
                "Expected dictionary of %s, not a %s" % (tag, str(item))
            )
        return (tag, dict(item))

    @staticmethod
    def _marshal_to_ids(tag, id_dict, index, libvirtxml, idtag):
        """Convert xml object to dictionary"""
        del index
        del libvirtxml
        if tag != idtag:
            return None
        return dict(id_dict)

    @staticmethod
    def marshal_from_uids(item, index, libvirtxml):
        """Convert dictionary to xml object"""
        return VMIDMapXML._marshal_from_ids(item, index, libvirtxml, "uid")

    @staticmethod
    def marshal_to_uids(tag, uid_dict, index, libvirtxml):
        """Convert xml object to dictionary"""
        func = lambda w, x, y, z: VMIDMapXML._marshal_to_ids(w, x, y, z, "uid")
        return func(tag, uid_dict, index, libvirtxml)

    @staticmethod
    def marshal_from_gids(item, index, libvirtxml):
        """Convert dictionary to xml object"""
        return VMIDMapXML._marshal_from_ids(item, index, libvirtxml, "gid")

    @staticmethod
    def marshal_to_gids(tag, gid_dict, index, libvirtxml):
        """Convert xml object to dictionary"""
        func = lambda w, x, y, z: VMIDMapXML._marshal_to_ids(w, x, y, z, "gid")
        return func(tag, gid_dict, index, libvirtxml)
