from threading import Lock
try:
    from collections import UserDict as IterableUserDict
except ImportError:
    from UserDict import IterableUserDict
from collections import OrderedDict

from avocado.core import exceptions

from six.moves import xrange


class ParamNotFound(exceptions.TestSkipError):
    pass


class Params(IterableUserDict):

    """
    A dict-like object passed to every test.
    """
    lock = Lock()

    def __getitem__(self, key):
        """ overrides the error messages of missing params[$key] """
        try:
            return IterableUserDict.__getitem__(self, key)
        except KeyError:
            raise ParamNotFound("Mandatory parameter '%s' is missing. "
                                "Check your cfg files for typos/mistakes" %
                                key)

    def get(self, key, default=None):
        """ overrides the behavior to catch ParamNotFound error"""
        try:
            return self[key]
        except ParamNotFound:
            return default

    def setdefault(self, key, failobj=None):
        if key not in self:
            self[key] = failobj
        return self[key]

    def objects(self, key):
        """
        Return the names of objects defined using a given key.

        :param key: The name of the key whose value lists the objects
                (e.g. 'nics').
        """
        lst = self.get(key, "").split()
        # remove duplicate elements
        objs = list({}.fromkeys(lst).keys())
        # sort list to keep origin order
        objs.sort(key=lst.index)
        del lst
        return objs

    def object_params(self, obj_name):
        """
        Return a dict-like object containing the parameters of an individual
        object.

        This method behaves as follows: the suffix '_' + obj_name is removed
        from all key names that have it.  Other key names are left unchanged.
        The values of keys with the suffix overwrite the values of their
        suffixless versions.

        :param obj_name: The name of the object (objects are listed by the
                objects() method).
        """
        suffix = "_" + obj_name
        self.lock.acquire()
        new_dict = self.copy()
        self.lock.release()
        for key in list(new_dict.keys()):
            if key.endswith(suffix):
                new_key = key.split(suffix)[0]
                new_dict[new_key] = new_dict[key]
        return new_dict

    def object_counts(self, count_key, base_name):
        """
        This is a generator method: to give it the name of a count key and a
        base_name, and it returns an iterator over all the values from params
        """
        count = self.get(count_key, 1)
        # Protect in case original is modified for some reason
        cpy = self.copy()
        for number in xrange(1, int(count) + 1):
            key = "%s%s" % (base_name, number)
            yield (key, cpy.get(key))

    def copy_from_keys(self, keys):
        """
        Return sub dict-like object by keys

        :param keys: white lists of key
        :return: dict-like object
        """
        new_dict = self.copy()
        new_dict.clear()
        for key in keys:
            if self.get(key):
                new_dict[key] = self.get(key)
        return new_dict

    def get_boolean(self, key, default=False):
        """
        Check if a config option is set to a default affirmation or not.

        :param key: config option key
        :type key: str
        :param bool default: whether to assume "yes" or "no" if param
                             does not exist (defaults to False/"no").
        :return whether option is set to 'yes'
        :rtype: bool
        """
        value = self.get(key, "yes" if default else "no")
        if value in ("yes", "on", "true"):
            return True
        if value in ("no", "off", "false"):
            return False
        raise ValueError("Cannot get boolean parameter value for %s: %s", key, value)

    def get_numeric(self, key, default=0, target_type=int):
        """
        Get numeric value converting to integer if necessary.

        :param str key: config option key
        :param int default: default numeric value
        :param type target_type: numeric type to return like int or float
        :return numerical type `target_type` converted parameter value
        :rtype: int or float
        """
        return target_type(self.get(key, default))

    def get_list(self, key, default="", delimiter=None, target_type=str):
        """
        Get a parameter value that is a character delimited list.

        :param str key: parameter whose value is list
        :param str default: default list value
        :param delimiter: character to split list items
        :type delimiter: str or None
        :param type target_type: type of each item, default is string
        :returns: empty list if if the key is not in the parameters
        :rtype: [str]

        .. note:: This an extension to the :py:func:`Params.objects` method as
          it allows for delimiters other than white space.
        .. seealso:: :py:func:`param_dict`
        """
        param_string = self.get(key, default)
        if not param_string:
            return []
        else:
            return [target_type(entry) for entry in param_string.split(delimiter)]

    def get_dict(self, key, default="", delimiter=None, need_order=False):
        """
        Get a param value that has the form 'name1=value1 name2=value2 ...'.

        :param str key: parameter whose value is dict
        :param str default: default dict value
        :param str delimiter: character to split list items
        :type delimiter: str or None
        :param bool need_order: whether to return an OrderedDict instead of
                                a regular dict
        :returns: empty dict if if the key is not in the parameters, a dict
                  or an ordered dictionary if the item order is important
        :rtype: {str: str}

        This uses :py:meth:`get_list` to convert the list entries to dict.
        """
        if need_order:
            result = OrderedDict()
        else:
            result = dict()
        for entry in self.get_list(key, default, delimiter):
            index = entry.find('=')
            if index == -1:
                raise ValueError('failed to find "=" in "{0}" (value for {1})'
                                 .format(entry, key))
            result[entry[:index].strip()] = entry[index+1:].strip()
        return result

    def drop_dict_internals(self):
        """
        Drop internal keys which are not of our concern and
        return the modified params.

        :returns: parameters without the internal keys
        :rtype: {str, str}
        """
        return Params({key: value for key, value in self.items() if not key.startswith("_")})
