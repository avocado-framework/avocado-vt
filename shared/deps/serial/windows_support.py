
import win32security
import win32file
import win32event
import win32con
import win32api
import pywintypes


class WinBufferedReadFile(object):
    verbose = False

    def __init__(self, filename):
        self._hfile = win32file.CreateFile(filename,
                                           win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                                           win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
                                           win32security.SECURITY_ATTRIBUTES(),
                                           win32con.OPEN_EXISTING,
                                           win32con.FILE_FLAG_OVERLAPPED,
                                           0)
        self._read_ovrlpd = pywintypes.OVERLAPPED()
        self._read_ovrlpd.hEvent = win32event.CreateEvent(None, True,
                                                          False, None)
        self._write_ovrlpd = pywintypes.OVERLAPPED()
        self._write_ovrlpd.hEvent = win32event.CreateEvent(None, True,
                                                           False, None)
        self._bufs = []
        self._n = 0

    def __del__(self):
        win32api.CloseHandle(self._read_ovrlpd.hEvent)
        win32api.CloseHandle(self._write_ovrlpd.hEvent)

    def close(self):
        win32api.CloseHandle(self._hfile)

    def write(self, s):
        win32file.WriteFile(self._hfile, s, self._write_ovrlpd)
        win32file.GetOverlappedResult(self._hfile, self._write_ovrlpd, True)

    def flush(self):
        pass  # TODO: flush in win32file?

    def read(self, n):
        while True:  # emulate blocking IO
            if self._n >= n:
                frags = []
                frags_length = 0
                if self.verbose:
                    txt = "get %s, | bufs = %s " % (n, self._n)
                    txt += "[%s]" % ','.join(map(lambda x: str(len(x)),
                                                 self._bufs))
                    print(txt)
                while frags_length < n:
                    frags.append(self._bufs.pop(0))
                    frags_length += len(frags[-1])
                self._n -= n
                whole = ''.join(frags)
                ret = whole[:n]
                rest = whole[n:]
                if len(rest) > 0:
                    self._bufs.append(rest)
                if self.verbose:
                    txt = "return %s(%s), | bufs = %s " % (len(ret), n,
                                                           self._n)
                    txt += "[%s]" % ','.join(map(lambda x: str(len(x)),
                                                 self._bufs))
                    print(txt)
                return ret
            try:
                # 4096 is the largest result viosdev will return right now.
                err, b = win32file.ReadFile(self._hfile, 4096,
                                            self._read_ovrlpd)
                nr = win32file.GetOverlappedResult(self._hfile,
                                                   self._read_ovrlpd,
                                                   True)
                if nr > 0:
                    self._bufs.append(b[:nr])
                    self._n += nr
                if self.verbose:
                    txt = "read %s, err %s | bufs = %s " % (nr, err, self._n)
                    txt += "[%s]" % ','.join(map(lambda x: str(len(x)),
                                                 self._bufs))
                    print(txt)
            except Exception:
                pass
        # Never Reached
        raise Exception("Error in WinBufferedReadFile - should never be reached")
