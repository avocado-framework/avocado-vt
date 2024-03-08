import logging

from managers import resbacking_mgr

LOG = logging.getLogger("avocado.service." + __name__)


def startup_resbacking_mgr():
    LOG.info(f"Startup the resource backing manager")
    return resbacking_mgr.startup()


def teardown_resbacking_mgr():
    LOG.info(f"Teardown the resource backing manager")
    return resbacking_mgr.teardown()


def connect_pool(pool_id, pool_config):
    """
    Connect to a specified resource pool.

    :param pool_id: The resource pool id
    :type pool_id: string
    :param pool_config: The resource pool configuration
    :type pool_config: dict
    :return: Succeeded: 0, {}
             Failed: 1, {"out": error message}
    :rtype: tuple
    """
    LOG.info(f"Connect to pool {pool_id}")
    return resbacking_mgr.create_pool_connection(pool_id, pool_config)


def disconnect_pool(pool_id):
    """
    Disconnect from a specified resource pool.

    :param pool_id: The resource pool id
    :type pool_id: string
    :param pool_config: The resource pool configuration
    :type pool_config: dict
    :return: Succeeded: 0, {}
             Failed: 1, {"out": error message}
    :rtype: tuple
    """
    LOG.info(f"Disconnect from pool {pool_id}")
    return resbacking_mgr.destroy_pool_connection(pool_id)


def create_backing_object(backing_config):
    """
    Create a resource backing object on the worker node, which is bound
    to one resource only

    :param backing_config: The resource backing configuration, usually,
                           it's a snippet of the resource configuration,
                           required for allocating the resource
    :type backing_config: dict
    :return: Succeeded: 0, {"out": backing_id}
             Failed: 1, {"out": error message}
    :rtype: tuple
    """
    LOG.info(
        "Create the backing object for the resource %s", backing_config["meta"]["uuid"]
    )
    return resbacking_mgr.create_backing_object(backing_config)


def destroy_backing_object(backing_id):
    """
    Destroy the backing

    :param backing_id: The cluster resource id
    :type backing_id: string
    :return: Succeeded: 0, {}
             Failed: 1, {"out": error message}
    :rtype: tuple
    """
    LOG.info(f"Destroy the backing object {backing_id}")
    return resbacking_mgr.destroy_backing_object(backing_id)


def get_resource_info_by_backing(backing_id):
    """
    Get the information of a resource by a specified backing

    We need not get all the information of the resource, because we can
    get the static information by the resource object from the master
    node, e.g. size, here we only get the information that only can be
    fetched from the worker nodes.

    :param backing_id: The backing id
    :type backing_id: string
    :return: Succeeded: 0, {"out": {snippet of the config}}
             Failed: 1, {"out": "error message"}
             e.g. a dir resource's config
             {
               "meta": {
                 "allocated": True,
               },
               "spec":{
                        "allocation": "1234567890",
                        'uri': '/p1/f1',
               }
             }
    :rtype: tuple
    """
    LOG.info(f"Info the resource by backing {backing_id}")
    return resbacking_mgr.get_resource_info_by_backing(backing_id)


def update_resource_by_backing(backing_id, config):
    """
    Update a resource by a specified backing

    :param backing_id: The resource backing id
    :type backing_id: string
    :param config: The specified action and the snippet of
                   the resource's spec and meta info used for update
    :type config: dict
    :return: Succeeded: 0, {"out": Depends on the command}
             Failed: 1, {"out": "error message"}
    :rtype: tuple
    """
    LOG.info(f"Update the resource by backing {backing_id}")
    return resbacking_mgr.update_resource_by_backing(backing_id, config)
