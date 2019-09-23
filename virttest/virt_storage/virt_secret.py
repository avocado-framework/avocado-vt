import os
import tempfile
import uuid

from avocado.utils import genio


class StorageSecret(object):

    def __init__(self, name, data, stype=None):
        self.name = name
        self._data = data
        self._data_file = None
        self.uuid = uuid.uuid1()
        self.secret_type = stype

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, data):
        if os.path.isfile(data):
            self.data_file = data
            self._data = genio.read_one_line(self.data_file)
        else:
            self._data = data

    @property
    def data_file(self):
        if self._data_file is None:
            self._data_file = tempfile.mktemp()
            genio.write_one_line(self._data_file, self.data)
        return self._data_file

    @data_file.setter
    def data_file(self, data_file):
        if os.path.isfile(data_file):
            self._data = genio.read_one_line(self.data_file)
        else:
            genio.write_one_line(data_file, self.data)


class StorageSecretAdmin(object):
    __secrets = list()

    @classmethod
    def secret_define_by_params(cls, name, params):
        data = params.get("secret_data", "")
        cls.__secrets.append(StorageSecret(name, data))
        return cls.__secrets[-1]

    @classmethod
    def secrets_define_by_params(cls, test_params):
        for name in test_params.objects("image_secrets"):
            params = test_params.object_params(name)
            cls.secret_define_by_params(name, params)

        return filter(lambda x: x.name == name, cls.__secrets)

    @classmethod
    def find_secret_by_name(cls, name):
        secrets = filter(lambda x: x.name == name, cls.__secrets)
        return secrets[0] if secrets else None

    @classmethod
    def find_secret_by_uuid(cls, _uuid):
        secrets = filter(lambda x: str(x.uuid) == _uuid, cls.__secrets)
        return secrets[0] if secrets else None


secret_admin = StorageSecretAdmin()
