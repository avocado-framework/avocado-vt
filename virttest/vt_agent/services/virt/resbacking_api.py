from ...managers.resbackings import _backing_mgr_dispatcher


def create_pool_connection(pool_config, pool_access):
    pool_id = pool_config['pool_id']
    pool_type = pool_config['pool_type']
    backing_mgr = _backing_mgr_dispatcher.dispatch_by_pool(pool_id)
    if backing_mgr is None:
        _backing_mgr_dispatcher.map_pool(pool_id, pool_type)
    backing_mgr = _backing_mgr_dispatcher.dispatch_by_pool(pool_id)
    backing_mgr.create_pool_connection(pool_config, pool_access)


def destroy_pool_connection(pool_id):
    backing_mgr = _backing_mgr_dispatcher.dispatch_by_pool(pool_id)
    backing_mgr.destroy_pool_connection(pool_id)
    _backing_mgr_dispatcher.unmap_pool(pool_id)

"""
def allocate(backing_id):
    backing_mgr = _backing_mgr_dispatcher.dispatch_by_backing(backing_id)
    backing_mgr.allocate(backing_id)


def release(backing_id):
    backing_mgr = _backing_mgr_dispatcher.dispatch_by_backing(backing_id)
    backing_mgr.release(backing_id)
"""


#def create_backing(config):
def create_backing(config, need_allocate=False):
    """
    Create a resource backing on the worker node, which is bound to one and
    only one resource, VT can access the specific resource allocation with
    the backing when starting VM on the worker node

    :param config: The config including the resource's meta and spec data
    :type config: dict
    :return: The resource id
    :rtype: string
    """
    pool_id = config['spec']['pool']
    backing_mgr = _backing_mgr_dispatcher.dispatch_by_pool(pool_id)
    #backing_id = backing_mgr.create_backing(config)
    backing_id = backing_mgr.create_backing(config, need_allocate)
    _backing_mgr_dispatcher.map_backing(backing_id, backing_mgr)
    return backing_id


#def destroy_backing(backing_id):
def destroy_backing(backing_id, need_release=False):
    """
    Destroy the backing, all resources allocated on worker nodes will be
    released.

    :param backing_id: The cluster resource id
    :type backing_id: string
    """
    backing_mgr = _backing_mgr_dispatcher.dispatch_by_backing(backing_id)
    #backing_mgr.destroy_backing(backing_id)
    backing_mgr.destroy_backing(backing_id, need_release)
    _backing_mgr_dispatcher.unmap_backing(backing_id)


def info_backing(backing_id):
    """
    Get the information of a resource with a specified backing

    We need not get all the information of the resource, because the
    static can be got by the resource object, e.g. size, here we only
    get the information which is dynamic, such as path and allocation

    :param resource_id: The backing id
    :type resource_id: string
    :return: The information of a resource, e.g.
             {
               'spec':{
                        'allocation': 12,
                        'path': [{'node1': '/p1/f1'},{'node2': '/p2/f1'}],
                      }
             }
    :rtype: dict
    """
    backing_mgr = _backing_mgr_dispatcher.dispatch_by_backing(backing_id)
    return backing_mgr.info_backing(backing_id)


def update_backing(backing_id, config):
    """
    :param backing_id: The resource backing id
    :type backing_id: string
    :param config: The specified action and the snippet of
                   the resource's spec and meta info used for update
    :type config: dict
    """
    backing_mgr = _backing_mgr_dispatcher.dispatch_by_backing(backing_id)
    backing_mgr.update_backing(backing_id, config)
