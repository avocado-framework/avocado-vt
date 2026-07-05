import unittest
from unittest.mock import Mock, patch

from virttest.test_setup.networking import BridgeConfig, NetworkProxies
from virttest.utils_params import Params


class TestProxySetuper(unittest.TestCase):
    def setUp(self):
        self._test_mock = Mock()
        self._env_mock = Mock()

        self._handler_mock = Mock()
        self._proxy_handler_mock = Mock()
        self._proxy_handler_mock.return_value = self._handler_mock

        self._opener_mock = Mock()
        self._build_opener_mock = Mock()
        self._build_opener_mock.return_value = self._opener_mock

        self._installer_mock = Mock()
        self._patchers = []
        self._patchers.append(
            patch("urllib.request.ProxyHandler", self._proxy_handler_mock)
        )
        self._patchers.append(
            patch("urllib.request.build_opener", self._build_opener_mock)
        )
        self._patchers.append(
            patch("urllib.request.install_opener", self._installer_mock)
        )
        for patcher in self._patchers:
            patcher.start()

    def tearDown(self):
        for patcher in self._patchers:
            patcher.stop()

    def test_no_config(self):
        params = {
            "other_key": "yes",
        }
        np = NetworkProxies(self._test_mock, params, self._env_mock)
        np.setup()
        self._proxy_handler_mock.assert_not_called()
        self._build_opener_mock.assert_not_called()
        self._installer_mock.assert_not_called()

    def test_empty_config(self):
        params = {
            "network_proxies": "",
            "other_key": "yes",
        }
        np = NetworkProxies(self._test_mock, params, self._env_mock)
        np.setup()
        self._proxy_handler_mock.assert_not_called()
        self._build_opener_mock.assert_not_called()
        self._installer_mock.assert_not_called()

    def test_invalid_config(self):
        params = {
            "network_proxies": "",
            "other_key": "yes",
        }
        np = NetworkProxies(self._test_mock, params, self._env_mock)
        np.setup()
        self._proxy_handler_mock.assert_not_called()
        self._build_opener_mock.assert_not_called()
        self._installer_mock.assert_not_called()

    def test_config_unique_proxy(self):
        params = {
            "network_proxies": "https_proxy: https://proxy.com:8080/",
            "other_key": "no",
        }
        proxies_dict = {"https": "https://proxy.com:8080/"}
        np = NetworkProxies(self._test_mock, params, self._env_mock)
        np.setup()
        self._proxy_handler_mock.assert_called_once_with(proxies_dict)
        self._build_opener_mock.assert_called_once_with(self._handler_mock)
        self._installer_mock.assert_called_once_with(self._opener_mock)

    def test_config_multiple_proxies(self):
        params = {
            "network_proxies": "https_proxy: https://proxy.com:8080/; "
            "ftp_proxy: ftp://proxy.com:3128/",
            "other_key": "no",
        }
        proxies_dict = {
            "https": "https://proxy.com:8080/",
            "ftp": "ftp://proxy.com:3128/",
        }
        np = NetworkProxies(self._test_mock, params, self._env_mock)
        np.setup()
        self._proxy_handler_mock.assert_called_once_with(proxies_dict)
        self._build_opener_mock.assert_called_once_with(self._handler_mock)
        self._installer_mock.assert_called_once_with(self._opener_mock)

    def test_config_half_valid_config(self):
        params = {
            "network_proxies": "https_proxy: https://proxy.com:8080/; "
            "nonsense: nonsense://bar.foo:0000; ",
            "other_key": "no",
        }
        proxies_dict = {"https": "https://proxy.com:8080/"}
        np = NetworkProxies(self._test_mock, params, self._env_mock)
        with self.assertRaises(ValueError):
            np.setup()


class TestBridgeSetuper(unittest.TestCase):
    def setUp(self):
        self._test_mock = Mock()
        self._env_mock = Mock()

    @patch("virttest.test_setup.networking.PrivateBridgeConfig")
    @patch("virttest.test_setup.networking.PrivateOvsBridgeConfig")
    def test_no_nics(self, ovs_mock, bridge_mock):
        params = Params({})
        brcfg = BridgeConfig(self._test_mock, params, self._env_mock)
        brcfg.setup()
        ovs_mock.setup.assert_not_called()
        bridge_mock.setup.assert_not_called()
        brcfg.cleanup()
        ovs_mock.cleanup.assert_not_called()
        bridge_mock.cleanup.assert_not_called()

    @patch("virttest.test_setup.networking.PrivateBridgeConfig")
    @patch("virttest.test_setup.networking.PrivateOvsBridgeConfig")
    def test_nics_not_private(self, ovs_mock, bridge_mock):
        params = Params(
            {
                "nics": "bridge",
                "netdst": "virbr0",
            }
        )
        brcfg = BridgeConfig(self._test_mock, params, self._env_mock)
        brcfg.setup()
        ovs_mock.setup.assert_not_called()
        bridge_mock.setup.assert_not_called()
        brcfg.cleanup()
        ovs_mock.cleanup.assert_not_called()
        bridge_mock.cleanup.assert_not_called()

    @patch("virttest.test_setup.networking.PrivateBridgeConfig")
    def test_nics_prbr(self, pbc_mock):
        mock_instance = Mock()
        pbc_mock.return_value = mock_instance
        params = Params(
            {
                "nics": "bridge",
                "netdst": "private",
                "priv_brname": "foobr0",
            }
        )
        brcfg = BridgeConfig(self._test_mock, params, self._env_mock)
        brcfg.setup()
        pbc_mock.assert_called_once_with(
            {
                "nics": "bridge",
                "netdst": "private",
                "priv_brname": "foobr0",
            }
        )
        mock_instance.setup.assert_called_once()
        pbc_mock.reset_mock()
        brcfg.cleanup()
        pbc_mock.assert_called_once_with(
            {
                "nics": "bridge",
                "netdst": "private",
                "netdst_bridge": "foobr0",
                "priv_brname": "foobr0",
            }
        )
        mock_instance.cleanup.assert_called_once()

    @patch("virttest.test_setup.networking.PrivateOvsBridgeConfig")
    def test_nics_ovs(self, povsbc_mock):
        mock_instance = Mock()
        povsbc_mock.return_value = mock_instance
        params = Params(
            {
                "nics": "ovs",
                "netdst": "private",
                "priv_br_type": "openvswitch",
            }
        )
        brcfg = BridgeConfig(self._test_mock, params, self._env_mock)
        brcfg.setup()
        povsbc_mock.assert_called_once_with(
            {
                "nics": "ovs",
                "netdst": "private",
                "priv_br_type": "openvswitch",
            }
        )
        mock_instance.setup.assert_called_once()
        povsbc_mock.reset_mock()
        brcfg.cleanup()
        povsbc_mock.assert_called_once_with(
            {
                "nics": "ovs",
                "netdst": "private",
                "priv_br_type": "openvswitch",
                "netdst_ovs": "atbr0",
            }
        )
        mock_instance.cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
