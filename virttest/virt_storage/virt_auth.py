import os

import configparser

from virttest.virt_storage.virt_secret import secret_admin


class StorageAuthation(object):

    def __init__(self, _type=None, username=None, password=None, secret=None):
        self.type = _type
        self.username = username
        self.password = password
        self.secret = secret

    @classmethod
    def auth_define_by_params(cls, params):
        instance = cls()
        auth_type = params.get("authorization_method")
        if auth_type == "chap":
            instance.password = params.get("chap_password")
            instance.username = params.get("chap_username")
        elif auth_type == "ceph":
            keyring = params.get("ceph_keyring")
            username = params.get("ceph_user")
            if keyring and os.path.isfile(keyring):
                config = configparser.ConfigParser()
                config.read(keyring)
                if not username:
                    username = config.sections()[0]
                password = config[username]["key"]
            else:
                password = params.get("ceph_key")
            instance.username = username
            instance.password = password

        secret_name = params.get("secret")
        if secret_name:
            secret = secret_admin.find_secret_by_name(secret_name)
            if not secret:
                secret_params = params.object_params(secret_name)
                secret = secret_admin.secret_define_by_params(
                    secret_name, secret_params)
            instance.secret = secret
        return instance
