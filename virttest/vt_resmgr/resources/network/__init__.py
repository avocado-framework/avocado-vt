from uuid import uuid1


class network(object):
    def __init__(self, name, params):
        self.uuid = str(uuid1())
        self.name = name
        self._type = params["type"]
        self._spec = params["spec"]

    def create(self):
        pass

    def delete(self):
        pass
