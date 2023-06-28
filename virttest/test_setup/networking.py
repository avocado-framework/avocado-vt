""" Define set/clean up procedures for network proxies
"""
import re
import urllib.request

from virttest.test_setup.core import Setuper


class NetworkProxies(Setuper):

    def setup(self):
        # enable network proxies setting in urllib2
        if self.params.get("network_proxies"):
            proxies = {}
            for proxy in re.split(r"[,;]\s*", self.params["network_proxies"]):
                proxy = dict([re.split(r"_proxy:\s*", proxy)])
                proxies.update(proxy)
            handler = urllib.request.ProxyHandler(proxies)
            opener = urllib.request.build_opener(handler)
            urllib.request.install_opener(opener)

    def cleanup(self):
        """ There is not any cleanup going on as the changes applied by
            installing the ProxyHandler are only applied to a the default
            global opener of urllib. That is, changes are only applied in the
            process in which such installation has taken place.
        """
        pass
