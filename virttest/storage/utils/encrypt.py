from avocado.utils import data_factory


class Luks(object):

    def __init__(self, _id=None, data=None):
        self._id = _id
        self._data = data

    @property
    def id(self):
        if self._id is None:
            self._id = data_factory.generate_random_string(4)
        return self._id

    @id.setter
    def id(self, _id=None):
        if _id is None:
            _id = data_factory.generate_random_string(4)
        self._id = _id

    @property
    def data(self):
        if self._data is None:
            self._data = data_factory.generate_random_string(6)
        return self._data

    @data.setter
    def data(self, _data=None):
        if _data is None:
            _data = data_factory.generate_random_string(6)
        self._data = _data

    def as_cmdline_object(self):

        return "-object secret,id=%s,data='%s'" % (self.name, self.data)

    def __str__(self):
        return self.as_qemu_object()

    def as_qmp_object(self):
        return {"key-secret": self.id, "format": "luks"}

    def as_qom_object(self):
        return {"qom_type": "secret", "id": self.id,
                "props": {"data": self.data}}
