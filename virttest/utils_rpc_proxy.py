import xmlrpc.client


def get_remote_proxy(uri, use_builtin_types=False):
    proxy = xmlrpc.client.ServerProxy(uri, allow_none=True,
                                      use_builtin_types=use_builtin_types)
    return proxy
