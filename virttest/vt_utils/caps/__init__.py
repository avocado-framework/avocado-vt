class Capabilities(object):
     """ Representation of capabilities. """

     def __init__(self):
         self._flags = set()

     def set_flag(self, flag):
         """
         Set the flag.

         :param flag: The name of flag.
         :type flag: Flags
         """
         self._flags.add(flag)

     def clear_flag(self, flag):
         """
         Clear the flag.

         :param flag: The name of flag.
         :type flag: Flags
         """
         self._flags.remove(flag)

     def __contains__(self, flag):
         return flag in self._flags

     def __len__(self):
         return len(self._flags)
