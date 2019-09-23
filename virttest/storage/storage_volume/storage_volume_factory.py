from virttest.storage.storage_pool import storage_pool_factory

from virttest.storage.storage_volume import exception
from virttest.storage.storage_volume import volume_format
from virttest.storage.storage_volume import volume_protocol
from virttest.storage.storage_volume import storage_volume


class VolumeProtocolFactory(object):

    @classmethod
    def factory(cls, name, pool, params):
        protocol = pool.protocol
        if protocol not in volume_protocol.SUPPORTED_VOLUME_PROTOCOL:
            raise exception.UnsupportedVolumeProtocolException(protocol)

        protocol_cls = volume_protocol.SUPPORTED_VOLUME_PROTOCOL[protocol]
        protocol_params = params.object_params(name)
        return protocol_cls(name, pool, protocol_params)


class VolumeFormatFactory(object):

    @classmethod
    def factory(cls, name, fmt, params):
        if fmt not in volume_format.SUPPORTED_VOLUME_FORMAT.keys():
            raise exception.UnsupportedVolumeFormatException(fmt)

        fmt_cls = volume_format.SUPPORTED_VOLUME_FORMAT[fmt]
        fmt_params = params.object_params(name)
        fmt_obj = fmt_cls(name, fmt_params)

        return fmt_obj


class StorageVolumeFactory:

    sp_manager = storage_pool_factory.StoragePoolFactory()

    def factory(cls, volume_name, test_params):

        def _build_volume(_volume_name):
            volume_params = test_params.object_params(_volume_name)
            volume_fmt = volume_params.get("image_format", "raw")
            sp_name = volume_params.get("storage_pool")
            sp = cls.sp_manager.get_pool_by_name(sp_name)
            sp.refresh()
            vol = sp.get_volume_by_name(_volume_name)
            if vol is None:
                vol = storage_volume.StorageVolume(_volume_name, sp, test_params)
                vol.fmt = VolumeFormatFactory.factory(
                    _volume_name, volume_fmt , test_params)
                vol.protocol = VolumeProtocolFactory.factory(
                    _volume_name, sp, test_params)
            else:
                if vol.fmt is None:
                    vol.fmt = VolumeFormatFactory.factory(
                        _volume_name, volume_fmt, test_params)
                if vol.protocol is None:
                    vol.protocol = VolumeProtocolFactory.factory(
                        _volume_name, sp, test_params)
            backing = volume_params.get("backing")
            if backing:
                for _vol in _build_volume(backing):
                    vol.backing = _vol
            yield vol

        volume = next(_build_volume(volume_name))
        volume.pool.volumes[volume_name] = volume
        return volume
