""" Define set/clean up procedures for network proxies
"""
import re
import urllib.request

from virttest.test_setup import PrivateBridgeConfig, PrivateOvsBridgeConfig
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
        """There is not any cleanup going on as the changes applied by
        installing the ProxyHandler are only applied to a the default
        global opener of urllib. That is, changes are only applied in the
        process in which such installation has taken place.
        """
        pass


class BridgeConfig(Setuper):
    def setup(self):
        setup_pb = False
        ovs_pb = False
        for nic in self.params.get("nics", "").split():
            nic_params = self.params.object_params(nic)
            if nic_params.get("netdst") == "private":
                setup_pb = True
                params_pb = nic_params
                self.params["netdst_%s" % nic] = nic_params.get("priv_brname", "atbr0")
                if nic_params.get("priv_br_type") == "openvswitch":
                    ovs_pb = True

        if setup_pb:
            if ovs_pb:
                brcfg = PrivateOvsBridgeConfig(params_pb)
            else:
                brcfg = PrivateBridgeConfig(params_pb)
            brcfg.setup()

    def cleanup(self):
        setup_pb = False
        ovs_pb = False
        for nic in self.params.get("nics", "").split():
            nic_params = self.params.object_params(nic)
            if nic_params.get("netdst") == "private":
                setup_pb = True
                params_pb = nic_params
                break
        else:
            setup_pb = self.params.get("netdst") == "private"
            params_pb = self.params

        if params_pb.get("priv_br_type") == "openvswitch":
            ovs_pb = True

        if setup_pb:
            if ovs_pb:
                brcfg = PrivateOvsBridgeConfig(params_pb)
            else:
                brcfg = PrivateBridgeConfig(params_pb)
            brcfg.cleanup()
