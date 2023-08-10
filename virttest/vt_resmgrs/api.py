"""
# Create a cluster level nfs resource
config = {'meta':{},'spec':{'size':123,'pool':'nfs_pool1','name':'stg'}}
res_id = create_resource(config)

# Bind the nfs resource to worker nodes(resource allocated)
args = {'bind': {'nodes': ['node1', 'node2'], 'pool': 'nfspool1'}}
update_resource(res_id, args)

# Unbind the nfs resource to node1
args = {'unbind': {'nodes': ['node1']}}
update_resource(res_id, args)

# Unbind the nfs resource(resource released)
args = {'unbind': {}}
update_resource(res_id, args)

# Destroy the nfs resource
destroy_resource(res_id)
"""


from .vt_resmgr import vt_resmgr


class PoolNotFound(Exception):
    def __init__(self, pool_id):
        self._id = pool_id

    def __str__(self):
        return 'Cannot find the pool(id="%s)"' % self._id


class UnknownPoolType(Exception):
    def __init__(self, pool_type):
        self._type = pool_type

    def __str__(self):
        return 'Unknown pool type "%s"' % self._type


class ResourceNotFound(Exception):
    pass


class ResourceBusy(Exception):
    pass


class ResourceNotAvailable(Exception):
    pass


class UnknownResourceType(Exception):
    pass


def register_resouce_pool(config):
    """
    Register a resource pool, the pool should be ready for
    use before registration

    :param config: The config includes the pool's meta and spec data,
                   e.g. {'meta':{'access':{}},'spec':{'name':'p1','id':'id1'}}
    :type config: dict
    :return: The resource pool id
    :rtype: string
    """
    pool_id = vt_resmgr.register_pool(config)
    if pool_id is None:
        raise UnknownPoolType(config['type'])
    return pool_id


def unregister_resouce_pool(pool_id):
    """
    Unregister a resource pool

    :param pool_id: The id of the pool to unregister
    :type pool_id: string
    """
    pool = vt_resmgr.get_pool_by_id(pool_id)
    if pool is None:
        raise PoolNotFound(pool_id)
    vt_resmgr.unregister_pool(pool_id)


def attach_resource_pool(pool_id):
    """
    Attach the registered pool to worker nodes, then the pool can be
    accessed by the worker nodes

    :param pool_id: The id of the pool to attach
    :type pool_id: string
    """
    pool = vt_resmgr.get_pool_by_id(pool_id)
    if pool is None:
        raise PoolNotFound(pool_id)
    vt_resmgr.attach_pool(pool_id)


def detach_resource_pool(pool_id):
    """
    Detach the pool from the worker nodes, after that, the pool cannot
    be accessed

    :param pool_id: The id of the pool to detach
    :type pool_id: string
    """
    pool = vt_resmgr.get_pool_by_id(pool_id)
    if pool is None:
        raise PoolNotFound(pool_id)
    vt_resmgr.detach_pool(pool_id)


def create_resource(config):
    """
    Create a logical resource without any specific resource allocation,
    the following is required to create a new resource:
      'meta':
        It depends on the specific resource
      'spec':
        'type': The resource type, e.g. 'volume'
        'pool': The id of the pool where the resource will be allocated
        The other attributes of a specific resource, e.g. the 'size' of
        a file-based volume
    Example:
      {'meta':{},'spec':{'size':123,'pool':'nfs_pool1','name':'stg'}}

    :param config: The config includes the resource's meta and spec data
    :type config: dict
    :return: The resource id
    :rtype: string
    """
    pool_id = config['spec']['pool']
    pool = vt_resmgr.get_pool_by_id(pool_id)
    if pool is None:
        raise PoolNotFound(pool_id)
    return pool.create_resource(config)


def destroy_resource(resource_id):
    """
    Destroy the logical resource, the specific resource allocation
    will be released

    :param resource_id: The resource id
    :type resource_id: string
    """
    pool = vt_resmgr.get_pool_by_resource(resource_id)
    pool.destroy_resource(resource_id)


def get_resource(resource_id):
    """
    Get all meta and spec information for a specified resource

    :param resource_id: The resource id
    :type resource_id: string
    :return: All the information of a resource, e.g.
             {
               'meta': {
                 'id': 'res_id1',
                 'permission': {
                     'owner': 'root',
                     'group': 'root',
                     'mode': '0755'
                 },
                 'bindings': [
                   {'node1': 'ref1'},
                   {'node2': 'ref2'}
                 ]
               },
               'spec': {
                 'pool': 'nfs_pool1',
                 'type': 'volume',
                 'size': 65536,
                 'name': 'stg',
                 'path': [{'node1': '/mnt1/stg'}, {'node2': '/mnt2/stg'}],
               }
             }
    :rtype: dict
    """
    pool = vt_resmgr.get_pool_by_resource(resource_id)
    return pool.info_resource(resource_id)


def update_resource(resource_id, config):
    """
    Update a resource, the command format:
      {'action': arguments}
    in which 'action' can be the following:
      'bind': Bind a specified resource to one or more worker nodes in order
              to access the specific resource allocation, note the allocation
              is done within the bind command
      'unbind': Unbind a specified resource from one or more worker nodes,
                the specific resource allocation will be released only when
                all bindings are gone
      'resize': Resize a resource, it's only available for the storage volume
                resource currently
    arguments is a dict object which contains all related settings for a
    specific action

    Examples:
      Bind a resource to one or more nodes
        {'bind': {'nodes': ['node1'], 'pool': 'nfspool1'}}
        {'bind': {'nodes': ['node1', 'node2'], 'pool': 'nfspool1'}}
      Unbind a resource from one or more nodes
        {'unbind': {'nodes': ['node1']}}
        {'unbind': {'nodes': ['node1', 'node2']}}
      Resize a specified storage volume resource
        {'resize': {'spec': {'size': 123456}}}

    :param resource_id: The resource id
    :type resource_id: string
    :param config: The specified action and its arguments
    :type config: dict
    """
    pool = vt_resmgr.get_pool_by_resource(resource_id)
    pool.update_resource(resource_id, config)
