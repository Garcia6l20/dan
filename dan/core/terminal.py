import atexit
import math
import time
import threading
import typing as t
import sys
import shutil
import weakref

from termcolor import colored

from dan.core import asyncio


class TermSequence:
    """Terminal sequence codes

    :see: https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797
    """

    ESC = "\x1b"
    SEQ_START = ESC + "["

    @staticmethod
    def home():
        """Moves cursor to home position (0, 0)"""
        return f"\x1b[H"

    @staticmethod
    def move(line, colomn=0):
        """Moves cursor down"""
        return f"\x1b[{line};{colomn}H"

    @staticmethod
    def up(n=1):
        """Moves cursor up"""
        return f"\x1b[{n}A"

    @staticmethod
    def down(n=1):
        """Moves cursor down"""
        return f"\x1b[{n}B"

    @staticmethod
    def next(n=1):
        """Moves cursor to next line"""
        return f"\x1b[{n}E"

    @staticmethod
    def prev(n=1):
        """Moves cursor to previous line"""
        return f"\x1b[{n}F"

    @staticmethod
    def left(n=1):
        """Moves cursor left"""
        return f"\x1b[{n}D"

    @staticmethod
    def right(n=1):
        """Moves cursor left"""
        return f"\x1b[{n}C"

    @staticmethod
    def hide_cursor():
        """Makes cursor invisible"""
        return f"\x1b[?25l"

    @staticmethod
    def show_cursor():
        """Makes cursor visible"""
        return f"\x1b[?25h"

    class hidden_cursor:
        def __enter__(self):
            sys.stdout.write(TermSequence.hide_cursor())

        def __exit__(self, *args):
            sys.stdout.write(TermSequence.show_cursor())

    @staticmethod
    def line_clear(n=2):
        """Erase line

        n == 0: erase from cursor to end of line
        n == 1: erase start of line to the cursor
        n == 2: erase the entire line
        """
        return f"\x1b[{n}K"

    __next_clear = next() + line_clear()

    @staticmethod
    def next_clear():
        """Moves to next line and clear it"""
        return TermSequence.__next_clear

    @staticmethod
    def sreen_clear(n=2):
        """Erase screen

        n == 0: erase from cursor until end of screen
        n == 1: erase from cursor to beginning of screen
        n == 2: erase entire screen
        n == 3: erase saved lines
        """
        return f"\x1b[{n}J"


class _OutputStreamProgress:
    UTF = " " + "".join(map(chr, range(0x258F, 0x2587, -1)))

    def __init__(self, stream: "TermStream", status: str, total=None) -> None:
        self._s = stream
        self._status = status
        self.total = total
        self.n = 0
        self._saved_status = None
        self._saved_extra = None
        self._elapsed_s = 0.0
        self._lock = asyncio.ThreadLock()

    async def __aenter__(self):
        self._t_start = time.time()
        self._saved_status = self._s._status
        self._saved_extra = self._s._extra
        self._s._status = self._status
        self._s._extra = self
        self._s.visible = True
        return self

    async def __aexit__(self, *args):
        self._s._status = self._saved_status
        self._s._extra = self._saved_extra

    async def __call__(self, n=1, status=None):
        with self._lock:
            self._elapsed_s = time.time() - self._t_start
            self.n += n
            if status is not None:
                self._s._status = self._status = status
        self._s.update()

    def __make_bar(self, frac, width):
        nsyms = len(self.UTF) - 1
        if frac is None:
            cursor_width = 3
            width -= cursor_width
            pos = 0.5 + math.sin(math.pi * self._elapsed_s) / 2
            offset, _ = divmod(pos * width * nsyms, nsyms)
            bar = (
                " " * int(offset)
                + self.UTF[-1] * cursor_width
                + " " * int(width - offset)
            )
        else:
            bar_length, frac_bar_length = divmod(int(frac * width * nsyms), nsyms)
            bar = self.UTF[-1] * bar_length
            if bar_length < width:  # whitespace padding
                bar = (
                    bar
                    + self.UTF[frac_bar_length]
                    + self.UTF[0] * (width - bar_length - 1)
                )
        return bar

    def __str__(self) -> str:
        with self._lock:
            if self.total is not None:
                frac = self.n / self.total
                rbar = f"{int(100 * frac):3d}%"
            else:
                frac = None
                rbar = "   ∞"
            width = self._s.width
            bar = self.__make_bar(frac, self._s._mngr.width // 5)
            padding = width - (len(bar) + len(rbar) + 5)
            padding = padding * " "
            return f"{padding}|{bar}| {rbar}"


class ColorTheme:
    def __init__(self, color: str, attrs: t.Iterable[str] = None) -> None:
        self.color = color
        self.attrs = attrs

    def __call__(self, s: str) -> t.Any:
        return colored(s, self.color, attrs=self.attrs)


class TermStreamColorTheme:
    default_icon = ColorTheme("grey", ["bold"])
    default_name = ColorTheme("blue", ["bold"])
    default_status = ColorTheme("grey", ["bold"])
    default_extra = ColorTheme("white")

    def __init__(
        self,
        icon: ColorTheme = None,
        name: ColorTheme = None,
        status: ColorTheme = None,
        extra: ColorTheme = None,
    ) -> None:
        self.icon = icon or self.default_icon
        self.name = name or self.default_name
        self.status = status or self.default_status
        self.extra = extra or self.default_extra


default_theme = TermStreamColorTheme()


class Toast:
    def __init__(self, stream: "TermStream") -> None:
        self._s = stream
        self._msg = None

    async def display(self, msg: str):
        async with self._s._lock:
            self._msg = msg
        self._s.update()

    async def delete(self):
        async with self._s._lock:
            self._s._toasts.remove(self)
        self._s.update()

    def __call__(self, msg: str):
        return self.display(msg)

    async def __aenter__(self):
        async with self._s._lock:
            self._s._toasts.append(self)
        return self

    async def __aexit__(self, *excs):
        await self.delete()


class TermStream:
    def __init__(
        self, name: str, theme: TermStreamColorTheme = None
    ) -> None:
        self.name = name
        self._lock = asyncio.ThreadLock()
        self._visible = False
        self._dirty = False
        self._icon = "◦"
        self._status: str = ""
        self._extra: str = ""
        self._toasts: list[Toast] = list()
        self.theme = theme or default_theme
        self._cached_str: str = None
        self._cached_height: int = 0
        self._mngr = manager()
        with self._mngr._lock:
            self._mngr._streams.add(self)

    @property
    def width(self):
        return self._mngr.width - (
            len(self._icon) + 1 + len(self.name) + 2 + len(self._status)
        )

    @property
    def visible(self):
        with self._lock:
            return self._visible

    @visible.setter
    def visible(self, value):
        with self._lock:
            self._visible = value
            self._dirty = True

    def hide(self):
        self.visible = False
        self.update()

    async def __hide_after(self, delay):
        await asyncio.sleep(delay)
        self.hide()

    async def status(self, msg: str, icon: str = None, timeout=None):
        async with self._lock:
            self._status = msg
            if icon is not None:
                self._icon = icon
            self._visible = True
        self.update()
        if timeout is not None:
            asyncio.create_task(self.__hide_after(timeout))

    def update(self):
        with self._lock:
            self._dirty = True
        self._mngr.update()

    def _refresh_state(self):
        return self._dirty, self._visible

    def progress(self, desc, total=None):
        return _OutputStreamProgress(self, desc, total=total)

    def toast(self):
        return Toast(self)

    ts = TermSequence

    def _get_output(self, now) -> str:
        if self._dirty:
            self._cached_height = 1
            self._cached_str = f"{self.theme.icon(self._icon)} {self.theme.name(self.name)}: {self.theme.status(self._status)}{self.theme.extra(self._extra)}"
            for toast in self._toasts:
                self._cached_str += f"{self.ts.next_clear()}    ➥  {toast._msg}"
                self._cached_height += 1
            self._dirty = False
        return self._cached_str, self._cached_height


class _TermManager:
    def __init__(self, max_update_time=1) -> None:
        self._streams: weakref.WeakSet[TermStream] = weakref.WeakSet()
        self._fp = sys.stdout
        self._lock = threading.RLock()
        self._wait_timeout = 1 / max_update_time
        self._up_ev = threading.Event()
        self._stop_requested = False
        self._raw_lines = list()
        self._thread = None

        global _manager
        if _manager is not None:
            raise RuntimeError('Only one _TermManager can be created')

    def __del__(self):
        self.stop()

    @property
    def height(self):
        return shutil.get_terminal_size()[1]

    @property
    def width(self):
        return shutil.get_terminal_size()[0]

    def start(self):
        if self._thread is not None:
            self.stop()
        self._thread = threading.Thread(target=self._render, daemon=True)
        self._thread.start()


    def stop(self):
        if self._thread is not None:
            with self._lock:
                self._stop_requested = True
                self._up_ev.set()
            self._thread.join()
            self._thread = None

    def update(self):
        self._up_ev.set()

    async def write(self, s: str):
        with self._lock:
            self._raw_lines.append(s)
            self.update()

    def _render(self):
        ts = TermSequence
        out = self._fp
        out.write(ts.home() + ts.sreen_clear())
        stop = False
        prev_line_count = 0
        with ts.hidden_cursor():
            while not stop:
                self._up_ev.wait()
                with self._lock:
                    self._up_ev.clear()
                    now = time.time()
                    stop = self._stop_requested
                    if prev_line_count:
                        out.write(ts.prev(prev_line_count))
                    prev_line_count = 0
                    force = False

                    if self._raw_lines:
                        out.write(ts.prev() + ts.sreen_clear())
                        out.writelines(self._raw_lines)
                        if self._raw_lines[-1][-1] != "\n":
                            out.write(ts.next())
                        self._raw_lines = list()
                        force = True

                for stream in self._streams:
                    with stream._lock:
                        is_dirty, is_visible = stream._refresh_state()
                        if is_dirty or force:
                            prev_height = stream._cached_height
                            out.write(ts.line_clear())
                            data, height = stream._get_output(now)
                            if is_visible:
                                if prev_height != height:
                                    force = True  # force re-render next streams
                                out.write(ts.line_clear())
                                out.write(data + ts.next())
                                prev_line_count += height
                            elif prev_height != 1:
                                force = True
                        elif is_visible:
                            # just jump over
                            prev_line_count += stream._cached_height
                            out.write(ts.next(stream._cached_height))
                # clear rest of the screen
                out.write(ts.sreen_clear(0))

_manager : _TermManager = None

def manager():
    global _manager
    if _manager is None:
        _manager = _TermManager()
        _manager.start()
        atexit.register(_cleanup_manager)
    return _manager

def _cleanup_manager():
    global _manager
    if _manager is not None:
        _manager.stop()
        del _manager

def write(s: str):
    return manager().write(s)
