"""AUTOtest implementation of iothread manager classes for QEMU."""

import itertools

from virttest.qemu_devices.qdevices import QIOThread


class IOThreadManagerBase(object):
    """Base class for iothread managers."""

    ID_PATTERN = "iothread%d"

    def __init__(self, iothreads=None):
        """
        Initialize iothread manager.

        :param iothreads: list of iothread objects, its id must conform to
                          ID_PATTERN.
        """
        self._iothread_finder = {}
        for iothread in iothreads or []:
            self._iothread_finder[iothread.get_aid()] = iothread
        self._index = itertools.count(len(iothreads))

    def find_iothread(self, iothread_id):
        """Find iothread with the id specified."""
        return self._iothread_finder.get(iothread_id)

    def _create_iothread(self):
        """Create and return new iothread object."""
        return QIOThread(self.ID_PATTERN % next(self._index))

    def request_iothread(self, iothread):
        """
        Return iothread object to use.

        Descendent classes should overwrite to perform different iothread
        schemes.

        :param iothread: iothread specified in params as `image_iothread`
        """
        raise NotImplementedError

    def release_iothread(self, iothread):
        """Release iothread."""
        iothread_id = iothread.get_aid()
        try:
            self._iothread_finder.pop(iothread_id)
        except KeyError:
            raise KeyError("iothread %s not exists" % iothread_id)


class PredefinedManager(IOThreadManagerBase):
    """
    Support legacy usage of iothread.
    ```
    iothreads = iothread0 iothread1
    iothread_image0 = iothread1
    ```
    """

    def request_iothread(self, iothread):
        """Request predefined iothread."""
        if iothread == "AUTO" or iothread == "auto":
            raise ValueError("Not support 'AUTO' request mode.")
        iothread_obj = self.find_iothread(iothread)
        if iothread_obj:
            return iothread_obj
        else:
            raise KeyError("Unable to find iothread %s" % iothread)


class RoundRobinManager(IOThreadManagerBase):
    """Dispatch iothread object in round-robin way."""

    @staticmethod
    def _iothread_cmpkey_getter(iothread):
        """Extract compare key for iothread object."""
        return (len(iothread.iothread_bus), iothread.get_aid())

    def request_iothread(self, iothread):
        """Return iothread with least device attached."""
        if iothread == "AUTO" or iothread == "auto":
            try:
                return min(
                    self._iothread_finder.values(), key=self._iothread_cmpkey_getter
                )
            except ValueError:
                raise KeyError("No available iothread to allocate")
        else:
            raise ValueError("Not support request specific iothread")


class OTOManager(IOThreadManagerBase):
    """Always dispatch new iothread object."""

    def request_iothread(self, iothread):
        """Return new iothread object."""
        if iothread == "AUTO" or iothread == "auto":
            iothread = self._create_iothread()
            self._iothread_finder[iothread.get_aid()] = iothread
            return iothread
        else:
            raise ValueError("Not support request specific iothread")


class MultiPeerRoundRobinManager(IOThreadManagerBase):
    """
    Dispatch iothread object in new round-robin way.
    Each iothreads will be allocated in round-robin way to the images.
    """

    def __init__(self, iothreads=None):
        """
        Initialize iothread manager.

        :param iothreads: list of iothread objects, its id must conform with
                          ID_PATTERN.
        :type iothreads: List
        """
        super().__init__(iothreads)
        self.__length = len(iothreads) if iothreads else 0
        self.__current_index = 0
        self.__pci_dev_iothread_vq_mapping = {}

    @property
    def pci_dev_iothread_vq_mapping(self):
        return self.__pci_dev_iothread_vq_mapping

    @pci_dev_iothread_vq_mapping.setter
    def pci_dev_iothread_vq_mapping(self, mapping):
        """
        Set the self.__pci_dev_iothread_vq_mapping
        :param mapping:
        :type mapping: dict, {string: iothread instance}
        """
        for key, val in mapping.items():
            if key in self.__pci_dev_iothread_vq_mapping:
                self.__pci_dev_iothread_vq_mapping[key].append(val)
            else:
                self.__pci_dev_iothread_vq_mapping[key] = [val]

    def request_iothread(self, iothread):
        """Return iothread.

        :param iothread: iothread.
        :type iothread: QIOThread
        :return: iothread.
        :rtype: QIOThread
        """
        if iothread == "AUTO" or iothread == "auto":
            iothread_aid = self.ID_PATTERN % (self.__current_index % self.__length)
            iothread = self.find_iothread(iothread_aid)
            self.__current_index += 1
            return iothread
        raise ValueError("Not support request specific iothread!")


class FullManager(IOThreadManagerBase):
    """Dispatch all iothread objects to an image device."""

    def __init__(self, iothreads=None):
        """
        Initialize iothread manager.

        :param iothreads: list of iothread objects, its id must conform with
                          ID_PATTERN.
        :type iothreads: List
        """
        super().__init__(iothreads)
        self.__iothreads_list = iothreads

    def request_iothread(self, iothread):
        """Return iothreads.

        :param iothread: iothread.
        :type iothread: QIOThread
        :return: the list of the iothreads.
        :rtype: List
        """
        if iothread == "AUTO" or iothread == "auto":
            return self.__iothreads_list
        raise ValueError("Not support request specific iothread!")
