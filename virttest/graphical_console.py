"""
Graphical Console
"""

import time
import os
import csv

from virttest import data_dir


_STR_DASH = '-'

KEYMAP_DIR = os.path.join(data_dir.get_shared_dir(), 'keymaps')


def get_keymap(keymap_file):
    """
    Get Key Mapping Table.

    :param keymap_file: a csv file that includes key mapping table info.
                        eg: "keymap_to_qcode.csv"
    :return: key mapping table info as a dict.
    """
    keymap = os.path.join(KEYMAP_DIR, keymap_file)
    with open(keymap, "r") as f:
        reader = csv.reader(f)
        keymap_dict = {}
        for row in reader:
            keymap_dict[row[0]] = row[1:]
        return keymap_dict


class UnsupportedKeyError(Exception):
    """
    Unsupported Key Error for Console
    """
    pass


class BaseConsole(object):
    """
    Base Console
    """
    KEY_DOWN = 1
    KEY_UP = 0

    def __init__(self, vm, logfile=None):
        self._vm = vm
        # TODO: logfile trace

    def key_press(self, keystroke, interval=0):
        """
        Key Press down.

        :param keystroke: pressed key, can be a single key or a combination key.
                          type is str, single key like 'a'.
                          combination key connect them with '-', like "Shift_L-a".
        :param interval: the interval between two keys, default interval=0.
        """

        for key in self._get_seq(keystroke, interval):
            self._key_event(self.KEY_DOWN, key)

    def key_release(self, keystroke, interval=0):
        """
        Key Release up.

        :param keystroke: released key, it happened behind press key.
                          if combination key was pressed, like "Shift_L-a",
                          will release key "a" first then release key "Shift_L".
        :param interval: the interval between two keys, default interval=0.
        """
        for key in self._get_seq(keystroke, interval):
            self._key_event(self.KEY_UP, key)

    def key_tap(self, keystroke, hold_time=0, interval=0):
        """
        Key Press down first, then Key Release up.

        :param keystroke: tap key, can be a single key or a combination key.
                          type is str, single key like 'a'.
                          combination key connect them with '-', like "Shift_L-a".
        :param hold_time: the time that keep one key pressed, default hole_time=0.
        :param interval: the interval between two keys, default interval=0.

        """
        self.key_press(keystroke, interval)
        self._hold_time(hold_time)
        keystroke = self._reverse(keystroke)
        self.key_release(keystroke, interval)

    def _hold_time(self, hold_time):
        """
        Time that keep one key pressed.
        """
        time.sleep(hold_time)

    @staticmethod
    def _get_seq(seq_str, interval):
        """
        Get sequence of seq_str.

        :param seq_str: key str, if have '-', seprate them by '-' sign,
                        and return them separately. if have not '-',
                        return orginal str.
        :param interval: the interval between return two value.
        """
        seq_str += _STR_DASH
        while True:
            val, seq_str = seq_str.split(_STR_DASH, 1)
            yield val
            if not seq_str.rstrip(_STR_DASH):
                break
            if interval:
                time.sleep(interval)

    @staticmethod
    def _reverse(seq_str):
        """
        Reversed seq_str.
        """
        seq = seq_str.split(_STR_DASH)
        seq.reverse()
        return _STR_DASH.join(seq)

    def _key_convert(self, key):
        """
        Key Convert.

        The method convert key name that defined in KEY_MAP_FILE.
        file to correct console excuteble code.

        :param key: key name.
        """
        raise NotImplementedError()

    def _key_event(self, event, key):
        """
        Send Key Event.

        :param event: key event.
        :param key: key name.
        """
        raise NotImplementedError()

    def close(self):
        pass


class DummyConsole(BaseConsole):

    """
    Dummy console
    """
    pass


class QMPConsole(BaseConsole):

    """
    QMP console
    """
    KEY_DOWN = True
    KEY_UP = False

    KEYMAP = get_keymap("keymap_to_qcode.csv")

    def key_press(self, keystroke, interval=0):
        """
        Key Press down.

        :param keystroke: pressed key, can be a single key or a combination key.
                          type is str, single key like 'a'.
                          combination key connect them with '-', like "Shift_L-a".
        :param interval: the interval between two keys, default interval=0.
        """
        if interval == 0:
            keys = self._get_seq(keystroke, interval)
            self._key_event(self.KEY_DOWN, keys)
        else:
            super(QMPConsole, self).key_press(keystroke, interval)

    def key_release(self, keystroke, interval=0):
        """
        Key Release up.

        :param keystroke: released key, it happened behind press key.
                          if combination key was pressed, like "Shift_L-a",
                          will release key "a" first then release key "Shift_L".
        :param interval: the interval between two keys, default interval=0.
        """
        if interval == 0:
            keys = self._get_seq(keystroke, interval)
            self._key_event(self.KEY_UP, keys)
        else:
            super(QMPConsole, self).key_release(keystroke, interval)

    def _key_convert(self, key):
        """
        Convert customer input key to QMP console executable key.

        :param key: type is str, key name that is defined in KEY_MAP_FILE.
        """
        try:
            value = self.KEYMAP[key][0]
        except KeyError:
            raise UnsupportedKeyError("%s does not supported" % key)
        return value

    def _key_event(self, down, keys):
        """
        Send key event.

        :param down: True or False, True for key down, False for key up.
        :param keys: send single key, type can be str or list, like 'a' or ['a'].
                     send combination key, type is list, like ['Shift_L', 'a'].
        """

        events = []
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            k = self._key_convert(key)
            event = {"type": "key",
                     "data": {"down": down,
                              "key": {"type": "qcode",
                                      "data": k}}}
            events.append(event)
        self._vm.qmp_monitors[0].input_send_event(events)


def GraphicalConsole(vm):
    klass = DummyConsole
    if getattr(vm, "qmp_monitors", None):
        klass = QMPConsole
    return klass(vm)
