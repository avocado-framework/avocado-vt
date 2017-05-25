"""
Classes and functions to handle storage vm migration.

Include features:
1. live snapshot
2. block mirror
3. block stream
4. live commit
5. transaction
"""
import logging

from avocado.core import exceptions


class StorageMigrationTest(object):

    """
    KVM classes for handling common operations of storage vm migration.
    """

    def __init__(self, params, env):
        """
        Init the default values for live snapshot object.

        :param params: A dict containing VM preprocessing parameters.
        :param env: The environment (a dict-like object).
        """
        self.params = params
        self.env = env
        self.vm = self.env.get_vm(self.params["main_vm"])


class LiveSnapshotTest(StorageMigrationTest):

    """
    KVM classes for handling operations of live snapshot.
    """

    def __init__(self, params, env, device, snapshot_file, **kwargs):
        """
        Init the default values for live snapshot object.

        :param params: A dict containing VM preprocessing parameters.
        :param env: The environment (a dict-like object).
        :param device: the name of the device to generate the snapshot from.
        :param snapshot_file: the target of the new image. A new file will be created.
        :param kwargs: optional keyword arguments to pass to func
        """
        StorageMigrationTest.__init__(self, params, env)
        self.device = device
        self.snapshot_file = snapshot_file
        self.kwargs = kwargs

    def create_snapshot(self):
        """
        Create a live disk snapshot.
        """
        output = self.vm.monitor.live_snapshot(self.device, self.snapshot_file,
                                               **self.kwargs)
        logging.debug(output)

    def check_snapshot(self):
        """
        Check whether the snapshot is created successfully.
        """
        snapshot_info = str(self.vm.monitor.info("block"))
        if self.snapshot_file not in snapshot_info:
            logging.error(snapshot_info)
            raise exceptions.TestFail("Snapshot doesn't exist")
        if self.kwargs.has_key('snapshot_node_name'):
            if self.kwargs['snapshot_node_name'] not in snapshot_info:
                logging.error(snapshot_info)
                raise exceptions.TestFail("There is no node name for snapshot")
