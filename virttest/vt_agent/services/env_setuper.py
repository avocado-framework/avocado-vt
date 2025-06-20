import logging

from vt_agent.drivers import env_setuper

LOG = logging.getLogger("avocado.service." + __name__)


def setup(setuper, setup_config={}):
    LOG.info(f"Setting up the {setuper} with {setup_config}")
    setuper = env_setuper.get_setuper(setuper)
    setuper.setup(setup_config)


def cleanup(setuper, clean_config={}):
    LOG.info(f"Cleaning up the {setuper} with {clean_config}")
    setuper = env_setuper.get_setuper(setuper)
    setuper.setup(clean_config)


def get_address_cache(hwaddr):
    # LOG.info(f"Getting the ip address of the MAC: {hwaddr}")
    sniffer = env_setuper.ip_sniffer
    ip_addr = sniffer.cache.get(hwaddr)
    return ip_addr


def drop_address_cache(hwaddr):
    # LOG.info(f"Droping the MAC: {hwaddr} from address cache")
    sniffer = env_setuper.ip_sniffer
    return sniffer.cache.drop(hwaddr)


def update_address_cache(cache):
    sniffer = env_setuper.ip_sniffer
    sniffer.cache.update(cache)


def clear_address_cache():
    sniffer = env_setuper.ip_sniffer
    sniffer.cache.clear()
