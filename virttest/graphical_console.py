"""
Graphical Console
"""

from __future__ import division
import time
import os
import csv
import math

from virttest import data_dir
from virttest import ppm_utils


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


def uniform_linear(duration, rate):
    """
    Uniform linear trace for mouse move.

    :param duration: the move duration time.
    :param rate: frequency of sending move event.
    :param src: start position.
    :param dst: destination position.

    :return: the object with a position in this line.
    :rtype: function for motion.
    """

    def motion(src, dst):
        start_x, start_y = src
        end_x, end_y = dst
        nr_samples = (duration * rate) if duration != 0 else 1
        dx = (end_x - start_x) / nr_samples
        dy = (end_y - start_y) / nr_samples
        x, y = start_x, start_y
        interval = (duration / nr_samples) if duration != 0 else 0
        while True:
            x += dx
            y += dy
            time.sleep(interval)
            if (abs(x - end_x) <= 1) and (abs(y - end_y) <= 1):
                break
            yield (round(x), round(y))
        yield (end_x, end_y)
    return motion


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

    BTN_DOWN = 1
    BTN_UP = 0

    SCROLL_FORWARD = 1
    SCROLL_BACKWARD = -1

    _pointer_pos = []

    def __init__(self, vm, logfile=None):
        self._vm = vm
        self._width, self._height = self.screen_size
        # TODO: screen size is changeable, should ensure they were synchronized before access.
        if not self._pointer_pos:
            self._set_pointer_pos((self._width//2, self._height//2))
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

    def btn_press(self, btnstroke, interval=0):
        """
        Press the button.

        :param btnstroke: button, like left, right, middle.
        :param interval: the interval between two buttons, default interval=0.
        """

        for btn in self._get_seq(btnstroke, interval):
            self._btn_event(self.BTN_DOWN, btn)

    def btn_release(self, btnstroke, interval=0):
        """
        Release the button.

        :param btnstroke: button, like left, right, middle.
        :param interval: the interval between two buttons, default interval=0.
        """

        for btn in self._get_seq(btnstroke, interval):
            self._btn_event(self.BTN_UP, btn)

    def btn_click(self, btnstroke, hold_time=0, interval=0):
        """
        Click the button.

        :param btnstroke: Mouse button, like left, right, middle.
        :param hold_time: the time that keep one btn pressed, default hole_time=0.
        :param interval: the interval between two btns, default interval=0.
        """

        self.btn_press(btnstroke, interval)
        self._hold_time(hold_time)
        btnstroke = self._reverse(btnstroke)
        self.btn_release(btnstroke, interval)

    def scroll_backward(self, count=1, interval=0):
        """
        Scroll the wheel to backward.

        :param count: scroll count, default count=1.
        :param interval: the interval between two scroll actions, default interval=0.
        """

        count -= 1
        for num in range(count):
            self._scroll_event(self.SCROLL_BACKWARD)
            if interval:
                time.sleep(interval)
        self._scroll_event(self.SCROLL_BACKWARD)

    def scroll_forward(self, count=1, interval=0):
        """
        Scroll the wheel to forward.

        :param count: scroll count, default count=1.
        :param interval: the interval between two scroll actions, default interval=0.
        """

        count -= 1
        for num in range(count):
            self._scroll_event(self.SCROLL_FORWARD)
            if interval:
                time.sleep(interval)
        self._scroll_event(self.SCROLL_FORWARD)

    def pointer_move(self, pos, motion=None, absolute=True):
        """
        Move the pointer to a given position.

        :param pos: pointer position as (x, y)
        :param motion: motion line, like uniform linear, default motion=None.
        :param absolute: True means motion with absolute coordinates,
                     False means motion with relatively coordinates.
        """

        if motion:
            for _pos in motion(self._pointer_pos, pos):
                self._motion_event(_pos, absolute)
        else:
            self._motion_event(pos, absolute)

    @property
    def screen_size(self):
        """
        Get the console screen size in pixels.
        Returns a tuple of 2 integers
        """

        raise NotImplementedError

    @property
    def pointer_pos(self):
        """
        Get the pointer position in console, the unit is pixel.
        Returns a tuple of 2 integers.
        """

        return self._pointer_pos

    @classmethod
    def _set_pointer_pos(cls, pos):
        """
        Set the pointer position in console, the unit is pixel.

        :param pos: a tuple of 2 integers.
        """

        cls._pointer_pos = pos

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

    def _btn_event(self, event, btn):
        """
        Send mouse button event.

        :param event: btn event.
        :param btn: mouse button.
        """
        raise NotImplementedError()

    def _scroll_event(self, event):
        """
        Send mouse scroll event.

        :param event: scroll event.
        """
        raise NotImplementedError()

    def _motion_event(self, pos, absolute=True):
        """
        Send mouse move event.

        :param pos: mouse position as (x,y).
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

    BTN_DOWN = True
    BTN_UP = False

    SCROLL_FORWARD = "wheel-up"
    SCROLL_BACKWARD = "wheel-down"

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

    def _btn_event(self, event, btn):
        """
        Send mouse button event.

        :param event: Button event, defined as True=down, False=up.
        :param btn: Mouse button.
        """

        events = [{"type": "btn",
                   "data": {"down": event,
                            "button": btn}}]
        self._vm.monitor.input_send_event(events)

    def _scroll_event(self, scroll):
        """
        Send mouse scroll event.

        :param scroll: scroll as vertical forward/backward or horizontal left/right.
                       But qmp only support scroll vertical forward/backward.
                       Does not support scroll horizontal left/right currently.
        """

        # send scroll event from qmp console also same with send btn event,
        # just btn equal to 'wheel-up/wheel-down'.
        self._btn_event(self.BTN_DOWN, scroll)

    def _motion_event(self, pos, absolute):
        """
        Send mouse motion event from qmp monitor.

        :param pos: Mouse position as (x, y).
        :param absolute: True means motion with absolute coordinates,
                     False means motion with relatively coordinates.
        """

        x, y = self._translate_pos_qmp(pos, absolute)
        mtype = 'abs' if absolute else 'rel'
        events = [{"type": mtype,
                   "data": {"axis": "x",
                            "value": int(x)}},
                  {"type": mtype,
                   "data": {"axis": "y",
                            "value": int(y)}}]
        self._vm.monitor.input_send_event(events)
        self._set_pointer_pos(pos)

    def _translate_pos_qmp(self, pos, absolute):
        """
        Translate position coordinates to qmp recognized coordinates.

        :param pos: Mouse position value as a tuple.
                    the pos value range in console as: x in 0 ~ screen width,
                    y in 0 ~ screen height.
        :param absolute: True means motion with absolute coordinates,
                     False means motion with relatively coordinates.

        :return: A tuple that translated position (x, y) for qmp.
        """

        if absolute:
            x = math.ceil(pos[0] * 32767 / self._width)
            y = math.ceil(pos[1] * 32767 / self._height)
        else:
            x = pos[0] - self._pointer_pos[0]
            y = pos[1] - self._pointer_pos[1]
        return (x, y)

    @property
    def screen_size(self):
        """
        Get the current screen size in pixels.
        Returns a tuple of 2 integers
        """

        tmp_dir = os.path.join(data_dir.get_tmp_dir(),
                               "graphic_console_%s" % self._vm.name)
        if not os.path.exists(tmp_dir):
            os.mkdir(tmp_dir)
        image = os.path.join(tmp_dir, "screendump")
        self._vm.monitor.screendump(image)
        return ppm_utils.image_size(image)


def GraphicalConsole(vm):
    klass = DummyConsole
    if getattr(vm, "qmp_monitors", None):
        klass = QMPConsole
    return klass(vm)
