import argparse

from avocado.core.settings import settings


def is_registering_settings_required():
    """Checks the characteristics of the Avocado settings API.

    And signals if the explicit registration of options is required, along
    with other API details that should be followed.

    The heuristic used here is to check for methods that are only present
    in the new API, and should be "safe enough".

    TODO: remove this once support for Avocado releases before 81.0,
    including 69.x LTS is dropped.
    """
    return all((hasattr(settings, 'add_argparser_to_option'),
                hasattr(settings, 'register_option'),
                hasattr(settings, 'as_json')))


if is_registering_settings_required():
    def get_opt(opt, name):
        """
        Compatibility handler to Avocado with configuration as dict

        :param opt: a configuration dict, usually from settings.as_dict()
        :param name: the name of the configuration key, AKA namespace
        """
        return opt.get(name)

    def set_opt(opt, name, value):
        """
        Compatibility handler to Avocado with configuration as dict

        :param opt: a configuration dict, usually from settings.as_dict()
        :param name: the name of the configuration key, AKA namespace
        :param value: the value to be set
        """
        opt[name] = value

    def set_opt_from_settings(opt, section, key, **kwargs):
        """No-op, default values are set at settings.register_option()."""
        pass

    def get_settings_value(section, key, **kwargs):
        namespace = '%s.%s' % (section, key)
        return settings.as_dict().get(namespace)

    def add_option(parser, arg, **kwargs):
        """Add a command-line argument parser to an existing option."""
        settings.add_argparser_to_option(
            namespace=kwargs.get('dest'),
            action=kwargs.get('action', 'store'),
            parser=parser,
            allow_multiple=True,
            long_arg=arg)

else:
    def get_opt(opt, name):
        """
        Compatibility handler for options in either argparse.Namespace or dict

        :param opt: either an argparse.Namespace instance or a dict
        :param name: the name of the attribute or key
        """
        if isinstance(opt, argparse.Namespace):
            return getattr(opt, name, None)
        else:
            return opt.get(name)

    def set_opt(opt, name, value):
        """
        Compatibility handler for options in either argparse.Namespace or dict

        :param opt: either an argparse.Namespace instance or a dict
        :param name: the name of the attribute or key
        :param value: the value to be set
        """
        if isinstance(opt, argparse.Namespace):
            setattr(opt, name, value)
        else:
            opt[name] = value

    def set_opt_from_settings(opt, section, key, **kwargs):
        """Sets option default value from the configuration file."""
        value = settings.get_value(section, key, **kwargs)
        namespace = '%s.%s' % (section, key)
        set_opt(opt, namespace, value)

    def get_settings_value(section, key, **kwargs):
        return settings.get_value(section, key, **kwargs)

    def add_option(parser, arg, **kwargs):
        """Adds new command-line argument option to the parser"""
        parser.add_argument(arg, **kwargs)
