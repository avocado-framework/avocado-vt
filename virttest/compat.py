import argparse


def get_opt(opt, name):
    """
    Compatibility handler for options in either argparse.Namespace or dict

    :param opt: either an argpase.Namespace instance or a dict
    :param name: the name of the attribute or key
    """
    if isinstance(opt, argparse.Namespace):
        return getattr(opt, name, None)
    else:
        return opt.get(name)


def set_opt(opt, name, value):
    """
    Compatibility handler for options in either argparse.Namespace or dict

    :param opt: either an argpase.Namespace instance or a dict
    :param name: the name of the attribute or key
    :param value: the value to be set
    """
    if isinstance(opt, argparse.Namespace):
        setattr(opt, name, value)
    else:
        opt[name] = value
