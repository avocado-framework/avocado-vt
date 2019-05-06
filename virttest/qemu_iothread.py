"""
Autotest implementation of iothread manager classes for QEMU.

These classes represents different iothread allocation schemes.
"""
import heapq
import itertools
import logging
import re

from avocado.utils import cpu
from virttest.qemu_devices.qdevices import QIOThread


class IOThreadScheme(object):
    """Represents data plane scheme for devices."""

    IOTHREAD_ON = 0
    IOTHREAD_OFF = 1
    IOTHREAD_SPECIFIED = 2
    IOTHREAD_EXCLUDED = 3

    def __new__(cls, *args, **kargs):
        """Create instance."""
        def method_factory(value):
            def method(self):
                return self.scheme == value

            method.__name__ = "is_%s" % attr.lower()
            return method.__get__(obj, cls)  # pylint: disable=E1121

        obj = object.__new__(cls)
        for attr, value in cls.__dict__.items():
            if attr.startswith("IOTHREAD"):
                method = method_factory(value)
                setattr(obj, method.__name__, method)
        return obj

    def __init__(self, iothread):
        """Initialize scheme."""
        self._scheme = IOThreadScheme.IOTHREAD_OFF
        self._iothread = None
        self.iothread = iothread

    @property
    def iothread(self):
        """Property iothread."""
        return self._iothread

    @iothread.setter
    def iothread(self, value):
        """Property iothread setter."""
        if value is None:
            self.scheme = IOThreadScheme.IOTHREAD_OFF
        else:
            self.scheme = IOThreadScheme.IOTHREAD_SPECIFIED
        self._iothread = value

    @property
    def scheme(self):
        """Property 'scheme."""
        return self._scheme

    @scheme.setter
    def scheme(self, value):
        """Property 'scheme' setter."""
        if value < 0 or value > 3:
            raise ValueError("Unsupported iothread scheme: '%s'" % value)
        self._scheme = value


class PriorityQueue(object):
    """Priority Queue."""

    REMOVED = '<removed-entry>'

    def __init__(self, items, key):
        self.counter = itertools.count()
        self.pq = []
        self.entry_finder = {}
        self.key = key
        for item in items:
            entry = self._format_entry(item)
            self.pq.append(entry)
            self.entry_finder[item] = entry
        heapq.heapify(self.pq)

    def _format_entry(self, item):
        return [self.key(item), next(self.counter), item]

    def __len__(self):
        return len(self.entry_finder)

    def __iter__(self):
        return iter(self.entry_finder)

    def remove_item(self, item):
        """Remove an item by marking it as REMOVED."""
        entry = self.entry_finder.pop(item)
        entry[-1] = PriorityQueue.REMOVED

    def add_item(self, item):
        """Add a new item or update the priority of an existing item."""
        if item in self.entry_finder:
            self.remove_item(item)
        entry = self._format_entry(item)
        self.entry_finder[item] = entry
        heapq.heappush(self.pq, entry)

    def pop_item(self):
        """Remove and return the lowest priority item."""
        while self.pq:
            item = heapq.heappop(self.pq)[-1]
            if item is not PriorityQueue.REMOVED:
                del self.entry_finder[item]
                return item
        raise KeyError("pop from an empty priority queue.")

    def get_lowest_item(self):
        """Get the item with lowest priority."""
        try:
            while True:
                if self.pq[0][-1] != PriorityQueue.REMOVED:
                    return self.pq[0][-1]
                heapq.heappop(self.pq)
        except KeyError:
            raise KeyError("get item with lowest priority from "
                           "an empty priority queue.")


class _IDGenerator(object):
    """ID generator."""

    def __init__(self, start=0):
        self.start = start
        self.occupied = set()

    def request_id(self):
        """Request an unoccupied id to use."""
        while self.start in self.occupied:
            self.start += 1
        return self.start

    def occupy_id(self, identifier):
        """Occupy a requested id."""
        self.occupied.add(identifier)

    def release_id(self, identifier):
        """Release an occupied id."""
        if identifier < self.start:
            self.start = identifier
        try:
            self.occupied.remove(identifier)
        except KeyError:
            pass


class IOThreadManagerError(Exception):
    """Base exception for iothread manager related errors."""


class IOThreadNotExistedError(IOThreadManagerError):
    """iothread not existed."""

    def __init__(self, iothread_id, manager):
        msg = "%s is not existed in %s." % (iothread_id, manager)
        super(IOThreadNotExistedError, self).__init__(msg)
        self.iothread_id = iothread_id
        self.manager = manager


class IOThreadAlreadyExistsError(IOThreadManagerError):
    """iothread object already exists in manager."""

    def __init__(self, iothread_id, manager):
        msg = "%s already exists in %s" % (iothread_id, manager)
        super(IOThreadAlreadyExistsError, self).__init__(msg)
        self.iothread_id = iothread_id
        self.manager = manager


class IOThreadManagerBase(object):
    """Base class for iothread manager.

    Steps to use:
    1. call request_iothread to get next available iothread id.
    2. call allocate_iothread to get the iothread corresponding to the id
    requested in step1.
    3. call bind_device_with_iothread to bind deivce to iothread.
    4. if the iothread allocated is a new one, should call activate_iothread to
    push into the iothread manager.
    5. call unbind_device_with_iothread to unbind device to iothread.
    6. call deactivate_iothread to pop out iothread from the iothread manager.
    """

    id_pattern = "iothread%d"

    def __init__(self, pool):
        self.iothread_pool = pool
        self.iothread_finder = {iothread.get_aid(): iothread
                                for iothread in pool}
        self.idgen = _IDGenerator()
        for iothread_id in self.iothread_finder.keys():
            self.idgen.occupy_id(self._get_index(iothread_id))

    @staticmethod
    def _get_index(iothread_id):
        """Get iothread index from iothread_id."""
        return int(re.match(r"iothread(\d+)", iothread_id).group(1))

    def __iter__(self):
        return iter(self.iothread_pool)

    def __str__(self):
        return "%s: [%s]" % (self.__class__.__name__, ', '.join(
            [it.str_short() for it in self]))

    def find_iothread(self, iothread_id):
        """Find existing iothread with id specified."""
        return self.iothread_finder.get(iothread_id)

    def request_iothread(self, iothread_id=None):
        """Request an unoccupied iothread id to use.

        :param iothread_id: requested iothread id if presented.
        """
        raise NotImplementedError

    def allocate_iothread(self, iothread_id):
        """Allocate iothread based on the id specified.

        This will either get existed iothread or create new iothread object,

        :param iothread_id: iothread_id returned from request_iothread.
        """
        raise NotImplementedError

    def bind_device_with_iothread(self, device, iothread_id):
        """Bind device with iothread.

        :notice: iothread should be activated, aka pushed into manager.
        :param dev: device to bind.
        :param iothread_id: id of iothread to update.
        """
        iothread = self.find_iothread(iothread_id)
        if iothread is None:
            raise IOThreadNotExistedError(iothread_id, self)
        iothread.attach(device)

    def unbind_device_with_iothread(self, device, iothread_id):
        """Unbind device with iothread.

        :notice: iothread should be activated, aka pushed into manager.
        :param dev: device to remove.
        :param iothread_id: iothread id to update.
        """
        iothread = self.find_iothread(iothread_id)
        if iothread is None:
            raise IOThreadNotExistedError(iothread_id, self)
        iothread.detach(device)

    def _push_to_pool(self, iothread):
        """Push iothread into self.iothread_pool.

        :param iothread: iothread object.
        """
        raise NotImplementedError

    def _remove_from_pool(self, iothread):
        """Remove iothread from self.iothread_pool.

        :param iothread: iothread object.
        """
        raise NotImplementedError

    def activate_iothread(self, iothread):
        """Activate and push iothread into manager."""
        iothread_id = iothread.get_aid()
        if self.find_iothread(iothread_id) is not None:
            raise IOThreadAlreadyExistsError(iothread_id, self)
        self._push_to_pool(iothread)
        self.iothread_finder[iothread_id] = iothread
        self.idgen.occupy_id(self._get_index(iothread_id))

    def deactivate_iothread(self, iothread):
        """Deactivate and remove iothread from manager."""
        if iothread.attached_devices_count() > 0:
            logging.warn("Try to remove a still-in-use iothread: %s",
                         iothread.str_short())
        iothread_id = iothread.get_aid()
        if self.find_iothread(iothread_id) is None:
            raise IOThreadNotExistedError(iothread_id, self)
        self._remove_from_pool(iothread)
        del self.iothread_finder[iothread_id]
        self.idgen.release_id(self._get_index(iothread_id))


class PredefinedManager(IOThreadManagerBase):
    """Predefined iothread allocation based on params.

    This provides backward support with previous patch that defines iothread
    objects with 'iothreads=...' and add to device with syntax:
    "iothread_image0 = iothread0"
    Naming convention for iothread: 'iothread[0-9]+'.
    """

    def __init__(self, iothreads):
        super(PredefinedManager, self).__init__(list(iothreads))

    def request_iothread(self, iothread_id=None):
        """Request a predefined iothread id to use."""
        if iothread_id is None:
            return None
        if self.find_iothread(iothread_id) is None:
            raise IOThreadNotExistedError(iothread_id, self)
        return iothread_id

    def allocate_iothread(self, iothread_id):
        """Allocate iothread based on the id specified for the device.

        For PredefinedManager, always return predefined iothread object.

        :param iothread_id: requested iothread id.
        """
        iothread = self.find_iothread(iothread_id)
        if iothread is None:
            raise IOThreadNotExistedError(iothread_id, self)
        return False, iothread

    def _push_to_pool(self, iothread):
        """Push iothread into self.iothread_pool.

        :param iothread: iothread object.
        """
        self.iothread_pool.append(iothread)

    def _remove_from_pool(self, iothread):
        """Remove iothread from self.iothread_pool.

        :param iothread: iothread object.
        """
        self.iothread_pool.remove(iothread)


def _iothread_key_getter(iothread):
    """Extract comparision key from iothread object."""
    # lambda or staticmethod is unpickable, define it as a function instead.
    return iothread.attached_devices_count(), iothread.get_aid()


class RoundRobinManager(IOThreadManagerBase):
    """Allocate iothread in round robin.

    Example:
    'iothread_scheme = roundrobin_3' will create 3 iothreads in manager, and
    the implementation with priority queue will always choose iothread object
    with the minimum devices attached. For iothreads with the same devices
    count, manager will choose iothread with least id index, for example,
    iothread0 is prior to iothread1.
    before allocation:  [iothread0 - 0, iothread1 - 0, iothread2 - 0]
    dev0 --> iothread0: [*iothread0 - 1, iothread1 - 0, iothread2 - 0]
    dev1 --> iothread1: [iothread0 - 1, *iothread1 - 1, iothread2 - 0]
    dev2 --> iothread2: [iothread0 - 1, iothread1 - 1, *iothread2 - 1]
    dev3 --> iothread0: [*iothread0 - 2, iothread1 - 1, iothread2 - 1]
    dev4 --> iothread1: [iothread0 - 2, *iothread1 - 2, iothread2 - 1]
    dev5 --> iothread2: [iothread0 - 2, iothread1 - 2, *iothread2 - 2]
    """

    def __init__(self, count=1):
        iothreads = [QIOThread(self.id_pattern % i) for i in range(count)]
        pool = PriorityQueue(iothreads, _iothread_key_getter)
        super(RoundRobinManager, self).__init__(pool)

    def request_iothread(self, iothread_id=None):
        """Request an iothread id to use."""
        if iothread_id is None:
            return self.iothread_pool.get_lowest_item().get_aid()
        if self.find_iothread(iothread_id) is None:
            raise IOThreadNotExistedError(iothread_id, self)
        else:
            return iothread_id

    def allocate_iothread(self, iothread_id):
        """Allocate iothread based on the id specified for the device.

        For RoundRobinManager, iothread allocated is always predefined.

        :param device: device that uses this iothread.
        :param iothread_id: requested iothread id.
        """
        iothread = self.find_iothread(iothread_id)
        if iothread is None:
            raise IOThreadNotExistedError(iothread_id, self)
        return False, self.iothread_finder[iothread_id]

    def bind_device_with_iothread(self, device, iothread_id):
        """Bind device with iothread.

        :param dev: device to bind.
        :param iothread_id: id of iothread to update.
        """
        super(RoundRobinManager,
              self).bind_device_with_iothread(device, iothread_id)
        # refresh priority in the pool
        self.iothread_pool.add_item(self.find_iothread(iothread_id))

    def unbind_device_with_iothread(self, device, iothread_id):
        """Unbind device with iothread.

        :param dev: device to bind.
        :param iothread_id: id of iothread to update.
        """
        super(RoundRobinManager,
              self).unbind_device_with_iothread(device, iothread_id)
        # refresh priority in the pool
        self.iothread_pool.add_item(self.find_iothread(iothread_id))

    def _push_to_pool(self, iothread):
        """Push iothread into self.iothread_pool.

        :param iothread: iothread object.
        """
        self.iothread_pool.add_item(iothread)

    def _remove_from_pool(self, iothread):
        """Remove iothread from self.iothread_pool.

        :param iothread: iothread object.
        """
        self.iothread_pool.remove_item(iothread)


class OTOManager(IOThreadManagerBase):
    """Create iothread for each controller device."""

    def __init__(self):
        super(OTOManager, self).__init__([])

    def request_iothread(self, iothread_id=None):
        """Request an iothread id to use."""
        return self.id_pattern % self.idgen.request_id()

    def allocate_iothread(self, iothread_id):
        """Allocate iothread based on the id specified for the device.

        Always create new iothread object for the id requested.

        :param device: device that uses this iothread.
        :param iothread_id: requested iothread id.
        """
        iothread = QIOThread(iothread_id=iothread_id)
        self.idgen.occupy_id(self._get_index(iothread_id))
        return True, iothread

    def _push_to_pool(self, iothread):
        """Push iothread into self.iothread_pool.

        :param iothread: iothread object.
        """
        self.iothread_pool.append(iothread)

    def _remove_from_pool(self, iothread):
        """Remove iothread from self.iothread_pool.

        :param iothread: iothread object.
        """
        self.iothread_pool.remove(iothread)


class OptimalManager(RoundRobinManager):
    """Dynamically allocate base on min(vpcu, pcpu, device)."""

    def __init__(self, vcpu):
        super(OptimalManager, self).__init__(count=0)
        self.cpu_boundary = min(vcpu, cpu.total_cpus_count())

    def request_iothread(self, iothread_id=None):
        """Request an iothread id to use."""
        # get new id if iothread count is less than cpu count.
        if len(self.iothread_pool) < self.cpu_boundary:
            return self.id_pattern % self.idgen.request_id()
        return super(OptimalManager, self).request_iothread(iothread_id)

    def allocate_iothread(self, iothread_id):
        """Allocate iothread based on the id specified for the device.

        :param device: device that uses this iothread.
        :param iothread_id: requested iothread id.
        """
        iothread = self.find_iothread(iothread_id)
        if iothread is None:
            iothread = QIOThread(iothread_id=iothread_id)
            self.idgen.occupy_id(self._get_index(iothread_id))
            return True, iothread
        return False, self.iothread_finder[iothread_id]
