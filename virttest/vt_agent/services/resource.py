from agents import resbacking_agent


def connect_pool(pool_id, pool_config):
    """
    Connect to a specified resource pool.

    :param pool_id: The resource pool id
    :type pool_id: string
    :param pool_config: The resource pool configuration
    :type pool_config: dict
    """
    resbacking_agent.create_pool_connection(pool_id, pool_config)


def disconnect_pool(pool_id):
    """
    Disconnect from a specified resource pool.

    :param pool_id: The resource pool id
    :type pool_id: string
    :param pool_config: The resource pool configuration
    :type pool_config: dict
    """
    resbacking_agent.destroy_pool_connection(pool_id)


def create_backing(backing_config):
    """
    Create a resource backing object on the worker node, which is bound
    to one resource only

    :param backing_config: The resource backing configuration, usually,
                           it's a snippet of the resource configuration,
                           required for allocating the resource
    :type backing_config: dict
    :return: The resource backing id
    :rtype: string
    """
    return resbacking_agent.create_backing(backing_config)


def destroy_backing(backing_id):
    """
    Destroy the backing

    :param backing_id: The cluster resource id
    :type backing_id: string
    """
    resbacking_agent.destroy_backing(backing_id)


def info_backing(backing_id, verbose=False):
    """
    Get the information of a resource with a specified backing

    We need not get all the information of the resource, because we can
    get the static information by the resource object from the master
    node, e.g. size, here we only get the dynamic information, such as
    file based volume path and allocation.

    :param resource_id: The backing id
    :type resource_id: string
    :param verbose: Get all information if verbose is True while
                    Get the required information if verbose is False
    :type verbose: boolean
    :return: The information of a resource, e.g.
             {
               'spec':{
                        'allocation': 12345,
                        'uri': '/p1/f1',
                      }
             }
    :rtype: dict
    """
    return resbacking_agent.info_backing(backing_id, verbose)


def update_backing(backing_id, config):
    """
    :param backing_id: The resource backing id
    :type backing_id: string
    :param config: The specified action and the snippet of
                   the resource's spec and meta info used for update
    :type config: dict
    """
    return resbacking_agent.update_backing(backing_id, config)
