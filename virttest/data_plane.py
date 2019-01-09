"""
Autotest implementation of iothread manager classes.

These classes represents different iothread allocation scheme.
"""
import heapq
import re

from avocado.utils import cpu
from virttest.qemu_devices.qdevices import IOThread


class MinQueue(object):
    """Min heap."""

    def __init__(self, item_list=None):
        """Heapify the pool."""
        self._queue = list(item_list or [])
        heapq.heapify(self._queue)

    def __len__(self):
        """Return the length."""
        return len(self._queue)

    def __iter__(self):
        """Return iterator."""
        return iter(self._queue)

    def __getitem__(self, pos):
        """heap.__getitem__(pos) <==> heap[pos]"""
        return self._queue[pos]

    def __setitem__(self, pos, value):
        """heap.__setitem__(pos, value) <==> heap[pos] = value"""
        self._queue[pos] = value

    def siftup(self, pos):
        """Rearrange if item on pos is increased in value."""
        heapq._siftup(self._queue, pos)

    def siftdown(self, pos, startpos=0):
        """Rearrange if item on pos is decreased in value."""
        heapq._siftdown(self._queue, startpos, pos)

    def siftup_item(self, item):
        """Rearrange item if its value is increased."""
        try:
            pos = self._queue.index(item)
            self.siftup(pos)
        except ValueError:
            pass

    def siftdown_item(self, item):
        """Rearrange item if its value is decreased."""
        try:
            pos = self._queue.index(item)
            self.siftdown(pos)
        except ValueError:
            pass

    def push(self, item):
        """Push item into heap."""
        heapq.heappush(self._queue, item)

    def pop(self):
        """Pop out the min item."""
        return heapq.heappop(self._queue)

    def get_min(self):
        """Return min item."""
        return self._queue[0]

    def remove(self, item):
        """Remove item and re-heapify."""
        if item not in self._queue:
            return
        self._queue.remove(item)
        heapq.heapify(self._queue)


class IOThreadManagerError(Exception):
    pass


class IOThreadNotExistedError(Exception):
    def __init__(self, iothread_id, manager):
        msg = "%s not existed in %s." % (iothread_id, manager)
        super(IOThreadNotExistedError, self).__init__(msg)
        self.iothread_id = iothread_id
        self.manager = manager


class IOThreadManagerBase(object):
    """
    Base class for iothread manager, only responsible for the allocation and
    deallocation of iothread object.

    To allocate iothread, call IOThreadManagerBase.get_iothread to get next
    available iothread object.
    After allocation, call IOThreadManagerBase.sync to update iothread and
    pool.

    TODO: sync with DevContainer in simple_hotplug and simple_unplug if the
    device plugged or unplugged is an instance of IOThread.
    """

    id_pattern = "iothread%d"

    def __init__(self, pool=None):
        """Constructor."""
        super(IOThreadManagerBase, self).__init__()
        if pool is None:
            pool = []
        self.iothread_pool = pool
        self.mapping = {iothread.id: iothread for iothread in pool}
        self.id_idx = 0
        self._loop_till_free()

    def _loop_till_free(self):
        while True:
            if self.id_pattern % self.id_idx not in self.mapping.keys():
                break
            self.id_idx += 1

    def _get_next_id(self):
        """Get next usable id."""
        id = self.id_pattern % self.id_idx
        return id

    def _release_id(self, id):
        """Release id."""
        try:
            id = int(re.match("iothread(\d+)", id).group(1))
        except (KeyError, ValueError, AttributeError):
            pass
        else:
            if id < self.id_idx:
                self.id_idx = id

    def __iter__(self):
        """Return iteractor."""
        return iter(self.iothread_pool)

    @property
    def iothread_count(self):
        """Return iothread count."""
        return len(self.iothread_pool)

    def get_iothread(self, iothread_id):
        """Get next iothread to use."""
        raise NotImplementedError

    def sync(self, dev, iothread_id):
        """
        Update iothread.

        :param dev: device attached.
        :param iothread_id: iothread id to update.
        """
        raise NotImplementedError

    def allocate_iothread(self, dev, iothread_id=None):
        """
        Update iothread and pool when unplug device.

        :param dev: device to unplug.
        :param iothread_id: iothread id.
        """
        raise NotImplementedError

    def update_iothread_in_unplug(self, dev, iothread_id, remove=False):
        """Update iothread when unplug device."""
        iothread = self.mapping[iothread_id]
        iothread.detach(dev)
        if remove is True:
            self.remove(iothread)

    def push(self, iothread):
        """Push iothread into manager."""
        raise NotImplementedError

    def remove(self, iothread):
        """Remove iothread from manager."""
        raise NotImplementedError

    def __str__(self):
        return "%s: [%s]" % (self.__class__.__name__,
                             ', '.join([str(it) for it in self.iothread_pool]))


class PredefinedManager(IOThreadManagerBase):
    """
    Predefined iothread allocation based on params, backward support with
    previous patch that defines iothread objects with 'iothreads=...' and add
    to device with bus_extra_params and blk_extra_params.
    """

    def __init__(self, iothreads):
        """Constructor."""
        super(PredefinedManager, self).__init__(list(iothreads))

    def get_iothread(self, iothread_id):
        """Allocate predefined iothread."""
        if (iothread_id is not None and
                iothread_id not in self.mapping):
            raise IOThreadNotExistedError(iothread_id, self)
        return iothread_id

    def sync(self, dev, iothread_id):
        """Update iothread with iothread_id."""
        iothread = self.mapping[iothread_id]
        iothread.attach(dev)
        self._loop_till_free()
        return False, iothread

    def allocate_iothread(self, dev, iothread_id):
        return self.sync(self.get_iothread(iothread_id), dev)

    def push(self, iothread):
        """Push iothread to manager."""
        iothread_id = iothread.id
        if iothread_id in self.mapping:
            return
        self.iothread_pool.append(iothread)
        self.mapping[iothread_id] = iothread

    def remove(self, iothread):
        """Remove iothread from manager."""
        iothread_id = iothread.id
        if iothread_id not in self.mapping:
            raise IOThreadNotExistedError(iothread_id, self)
        self._release_id(iothread_id)
        del self.mapping[iothread_id]
        self.iothread_pool.remove(iothread)


class RoundRobinManager(IOThreadManagerBase):
    """
    Allocate iothread in round robin.
    Example:
    'roundrobin3' will create 3 iothreads in manager, and the using of min heap
    will always choose iothread object with the minimum devices attached.
    before allocation:  [iothread0 - 0, iothread1 - 0, iothread2 - 0]
    dev0 --> iothread0: [*iothread0 - 1, iothread1 - 0, iothread2 - 0]
    dev1 --> iothread1: [iothread0 - 1, *iothread1 - 1, iothread2 - 0]
    dev2 --> iothread2: [iothread0 - 1, iothread1 - 1, *iothread2 - 1]
    dev3 --> iothread0: [*iothread0 - 2, iothread1 - 1, iothread2 - 1]
    dev4 --> iothread1: [iothread0 - 2, *iothread1 - 2, iothread2 - 1]
    dev5 --> iothread2: [iothread0 - 2, iothread1 - 2, *iothread2 - 2]
    """

    def __init__(self, count=1):
        """Constructor."""
        pool = [IOThread(self.id_pattern % i) for i in range(count)]
        super(RoundRobinManager, self).__init__(MinQueue(pool))

    def get_iothread(self, iothread_id=None):
        """Get next iothread id to use."""
        if iothread_id is None:
            return self.iothread_pool.get_min().id
        if iothread_id in self.mapping:
            return iothread_id
        # not existed iothread requested
        raise IOThreadNotExistedError(iothread_id, self)

    def sync(self, dev, iothread_id):
        """Update iothread and manager, return the synced iothread."""
        iothread = self.mapping[iothread_id]
        iothread.attach(dev)
        self.iothread_pool.siftup_item(iothread)
        self._loop_till_free()
        return False, iothread

    def allocate_iothread(self, dev, iothread_id=None):
        """
        Get iothread to use.

        param dev: device that requests iothread.
        param iothread_id: iothread_id to request, ignored.
        """
        return self.sync(self.get_iothread(), dev)

    def update_iothread_in_unplug(self, dev, iothread_id, remove=False):
        """Update iothread and pool when unplug device."""
        super(RoundRobinManager, self).update_iothread_in_unplug(dev,
                                                                 iothread_id,
                                                                 remove)
        if remove is False:
            iothread = self.mapping[iothread_id]
            self.iothread_pool.siftdown_item(iothread)

    def push(self, iothread):
        """Push iothread to manager."""
        iothread_id = iothread.id
        if iothread_id in self.mapping:
            return
        self.iothread_pool.push(iothread)
        self.mapping[iothread_id] = iothread

    def remove(self, iothread):
        """Remove iothread from manager."""
        iothread_id = iothread.id
        if iothread_id not in self.mapping:
            raise IOThreadNotExistedError(iothread_id, self)
        self._release_id(iothread_id)
        del self.mapping[iothread_id]
        self.iothread_pool.remove(iothread)


class OTOManager(IOThreadManagerBase):
    """Create iothread for each controller device."""

    def __init__(self):
        """Constructor."""
        super(OTOManager, self).__init__()

    def get_iothread(self, iothread_id=None):
        """Get next iothread id to use."""
        return self._get_next_id()

    def sync(self, dev, iothread_id):
        """Instantiate a iothread object with iothread_id."""
        iothread = IOThread(id=iothread_id)
        iothread.attach(dev)
        self.push(iothread)
        self._loop_till_free()
        return True, iothread

    def allocate_iothread(self, dev, iothread_id):
        return self.sync(self.get_iothread(), dev)

    def update_iothread_in_unplug(self, dev, iothread_id, remove=True):
        """Update iothread and pool in unplug, always remove iothread."""
        super(OTOManager, self).update_iothread_in_unplug(dev, iothread_id,
                                                          remove)

    def push(self, iothread):
        """Push iothread to manager."""
        iothread_id = iothread.id
        if iothread_id in self.mapping:
            return
        self.iothread_pool.append(iothread)
        self.mapping[iothread_id] = iothread

    def remove(self, iothread):
        """Remove iothread from manager."""
        iothread_id = iothread.id
        if iothread_id not in self.mapping:
            raise IOThreadNotExistedError(iothread_id, self)
        self._release_id(iothread_id)
        del self.mapping[iothread_id]
        self.iothread_pool.remove(iothread)


class OptimalManager(RoundRobinManager):
    """Dynamically allocate base on min(vpcu, pcpu, device)."""

    def __init__(self, vcpu):
        """Constructor."""
        super(OptimalManager, self).__init__(count=0)
        self.cpu_boundary = min(vcpu, cpu.total_cpus_count())

    def get_iothread(self, iothread_id=None):
        """Get next iothread id to use."""
        if len(self.iothread_pool) < self.cpu_boundary:
            return self._get_next_id()
        else:
            return super(OptimalManager, self).get_iothread()

    def sync(self, dev, iothread_id):
        """Instantiate a new iothread object with iothread_id."""
        if iothread_id in self.mapping:
            is_new = False
            iothread = self.mapping[iothread_id]
        else:
            is_new = True
            iothread = IOThread(id=iothread_id)
            self.push(iothread)
        iothread.attach(dev)
        self.iothread_pool.siftup_item(iothread)
        self._loop_till_free()
        return is_new, iothread

    def allocate_iothread(self, dev, iothread_id=None):
        return self.sync(self.get_iothread(), dev)

    def update_iothread_in_unplug(self, dev, iothread_id, remove=False):
        """Update iothread and pool in unplug."""
        iothread = self.mapping[iothread_id]
        # always remove empty iothread
        if (remove is False and
                len(iothread) == 1):
            remove = True
        super(OptimalManager, self).update_iothread_in_unplug(dev, iothread_id,
                                                              remove)
