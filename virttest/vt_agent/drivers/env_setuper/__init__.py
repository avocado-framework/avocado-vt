from .networking import IPSniffer

ip_sniffer = IPSniffer()

def get_setuper(setuper):
    setupers = {"ip_sniffer": ip_sniffer}
    if setuper not in setupers:
        raise NotImplementedError(f"No supported the setuper {setuper}")
    return setupers[setuper]
