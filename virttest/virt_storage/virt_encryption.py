from virttest.virt_storage.virt_secret import secret_admin


class VolumeEncryption(object):

    def __init__(self, encrypt_format=None, secret=None):
        self.format = encrypt_format
        self.secret = secret

    def __str__(self):
        return "%s: %s" % (self.__class__.__name__, self.format)

    @classmethod
    def encryption_define_by_params(cls, params):
        instance = cls()
        if params["image_encryption"] == "on":
            encryption_format = "aes"
        else:
            encryption_format = params["image_encryption"]
        instance.format = encryption_format
        secret_name = params["secret_name"]
        secret = secret_admin.find_secret_by_name(secret_name)
        if not secret:
            secret_params = params.object_params(secret_name)
            secret = secret_admin.secret_define_by_params(
                secret_name, secret_params)
        instance.secret = secret
        return instance
