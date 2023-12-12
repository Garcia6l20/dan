import atexit
import math
import time
import typing as t
import sys
import shutil
import weakref
import logging
import enum
from contextlib import nullcontext
from dan.core import asyncio

from termcolor import colored

from dan.core import asyncio


class TerminalMode(enum.Enum):
    BASIC = 1
    STICKY = 2
    CODE = 3


mode = TerminalMode.STICKY


def set_mode(new_mode: TerminalMode):
    global mode
    global _manager
    if _manager is not None:
        raise RuntimeError("Cannot change terminal mode once initialized")
    mode = new_mode


class TermSequence:
    """Terminal sequence codes

    :see: https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797
    """

    ESC = "\x1b"
    SEQ_START = ESC + "["

    @staticmethod
    def current_pos():
        return "\x1b[6n"

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
    def scroll_up(n=1):
        """Scroll viewport up"""
        return f"\x1b[{n}S"

    @staticmethod
    def scroll_down(n=1):
        """Scroll viewport up"""
        return f"\x1b[{n}T"

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

    def __init__(
        self, stream: "TermStream", status: str, total=None, auto_update=True
    ) -> None:
        self._s = stream
        self._status = status
        self.total = total
        self.n = 0
        self._saved_status = None
        self._saved_extra = None
        self._elapsed_s = 0.0
        self._auto_update = auto_update
        self._auto_update_task = None
        self._done = False

    async def __auto_update(self):
        while True:
            await asyncio.sleep(0.25)
            self.__call__(0)

    def __enter__(self):
        self._done = False
        self._t_start = time.time()
        self._saved_status = self._s._status
        self._saved_extra = self._s._extra
        self._s._status = self._status
        self._s._extra = self
        self._s.visible = True
        if self._auto_update:
            self._auto_update_task = asyncio.create_task(self.__auto_update())
        return self

    def __exit__(self, *args):
        self._done = True
        if self._auto_update_task is not None:
            self._auto_update_task.cancel()
            self._auto_update_task = None
        
        if mode == TerminalMode.CODE:
            # we want done/done to be printed
            def reset():
                self._s._status = self._saved_status
                self._s._extra = self._saved_extra
                self._s.update()
            self._s._mngr._flush_callbacks.append(reset)
        else:
            self._s._status = self._saved_status
            self._s._extra = self._saved_extra
        self._s.update()

    def __call__(self, n=1, status=None):
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

    def __str_code(self) -> str:
        if self._done:
            return 'done/done'
        return f'{self.n}/{self.total}'

    def __str_default(self) -> str:
        if self.total:
            frac = self.n / self.total
            rbar = f"{int(100 * frac):3d}%"
            eta = (1 - frac) * self._elapsed_s
            rbar += f" - eta: {int(eta)}s"
        else:
            frac = None
            rbar = "   ∞"
        bar = self.__make_bar(frac, self._s._mngr.width // 5)
        return f" |{bar}| {rbar}"

    def __str__(self) -> str:
        match mode:
            case TerminalMode.CODE:
                return self.__str_code()
            case _:
                return self.__str_default()


class _TaskGroup(asyncio.TaskGroup, _OutputStreamProgress):
    def __init__(self, stream: "TermStream", name: str, **kwargs):
        _OutputStreamProgress.__init__(self, stream, status=name, **kwargs)
        asyncio.TaskGroup.__init__(self, name)

    def __notify_bar_task_done(self, task):
        self._elapsed_s = time.time() - self._t_start
        self.n += 1
        self._s.update()

    async def __aexit__(self, et, exc, tb):
        total = len(self._tasks)
        if total:
            self.total = total
            for task in self._tasks:
                task.add_done_callback(self.__notify_bar_task_done)
            self._s.update()
        _OutputStreamProgress.__enter__(self)
        result = await asyncio.TaskGroup.__aexit__(self, et, exc, tb)
        _OutputStreamProgress.__exit__(self, et, exc, tb)
        # async def delayed_exit():
        #     await asyncio.sleep(0.5)
        #     _OutputStreamProgress.__exit__(self, et, exc, tb)
        # asyncio.spawn(delayed_exit())
        return result


class ColorTheme:
    def __init__(self, color: str, attrs: t.Iterable[str] = None) -> None:
        self.color = color
        self.attrs = attrs

    def __call__(self, s: str) -> t.Any:
        return colored(s, self.color, attrs=self.attrs)


class TermLogHandler(logging.Handler):
    def emit(self, record):
        write(self.format(record))


class TermStreamColorTheme:
    default_icon = ColorTheme("grey", ["bold"])
    default_name = ColorTheme("cyan", ["bold"])
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


class TermStream:
    DEFAULT_ICON = "➔"
    CHILD_ICON = "➥"

    def __init__(
        self, name: str, theme: TermStreamColorTheme = None, parent: "TermStream" = None
    ) -> None:
        self.name = name
        self._visible = False
        self._dirty = False
        self._icon = self.DEFAULT_ICON
        self._status: str = ""
        self._extra: str = ""
        self.theme = theme or default_theme
        self._cached_out: list[str] = list()
        self._mngr = manager()
        self._hide_task: asyncio.Task = None
        self._offset = 0
        self._parent = parent
        self._children: list[weakref.ReferenceType[TermStream]] = list()
        self._weak_self = weakref.ref(self)
        if self._parent is not None:
            self._offset = self._parent._offset + 2
            self._parent._children.append(self._weak_self)
            self._icon = self.CHILD_ICON
        else:
            self._mngr._streams.append(self._weak_self)

        match mode:
            case TerminalMode.CODE:
                self._get_output = self._get_output_code
                from dan.logging import _no_color_formatter
                self._formatter = _no_color_formatter
            case _:
                self._get_output = self._get_output_default

    def __del__(self):
        if self._parent:
            self._parent._children.remove(self._weak_self)
            self._parent.update()
        else:
            self._mngr._streams.remove(self._weak_self)
            self._mngr.update()

    def sub(self, name, theme: TermStreamColorTheme = None):
        return TermStream(name, theme, parent=self)

    @property
    def prefix_width(self):
        return self._mngr.width - (
            len(self._icon) + 1 + len(self.name) + 2 + self._offset
        )

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = value
        self._dirty = True

    def hide(self):
        self.visible = False
        self.update()

    def hide_children(self):
        for ref in self._children:
            ref().hide()
        self.update()

    async def __hide_after(self, delay):
        await asyncio.sleep(delay)
        self.hide()

    def __hide_task_done(self, t: asyncio.Task):
        if t.cancelled():
            self.hide()

    def status(self, msg: str, icon: str = None, timeout=None):
        self._status = msg
        if icon is not None:
            self._icon = icon
        self._visible = True
        if self._hide_task is not None:
            self._hide_task.remove_done_callback(self.__hide_task_done)
            self._hide_task.cancel()
            self._hide_task = None
        if timeout is not None:
            self._hide_task = asyncio.create_task(self.__hide_after(timeout))
            self._hide_task.add_done_callback(self.__hide_task_done)
        self.update()

    def update(self):
        self._dirty = True
        if not self._status:
            self._visible = False
        if self._parent is not None:
            self._parent.update()
        else:
            self._mngr.update()

    def _refresh_state(self):
        return self._dirty, self._visible

    def progress(self, desc, total=None, **kwargs):
        return _OutputStreamProgress(self, desc, total=total, **kwargs)

    def task_group(self, name):
        return _TaskGroup(self, name)

    ts = TermSequence

    def _get_output_code(self, now) -> list[str]:
        if self._dirty:
            from dan.logging import STATUS, PROGRESS
            if isinstance(self._extra, _OutputStreamProgress):
                record = logging.LogRecord(self.name, PROGRESS, '', 0, f'{self._status} - {self._extra}', None, None)
            else:
                record = logging.LogRecord(self.name, STATUS, '', 0, f'{self._status}', None, None)

            self._cached_out = [self._formatter.format(record) + '\n']
            for ref in self._children:
                child = ref()
                if child.visible:
                    self._cached_out.extend(child._get_output(now))
            self._dirty = False
        return self._cached_out

    def _get_output_default(self, now) -> list[str]:
        if self._dirty:
            prefix = f"{' ' * self._offset}{self.theme.icon(self._icon)}  {self.theme.name(self.name)}: "
            extra = str(self._extra)
            status = self._status.replace('\n', ' ') # TODO handle multiline status
            max_status_len = self.prefix_width - (len(extra)) - 1
            if len(status) > max_status_len:
                status = status[: max_status_len - 4] + " ..."
            if len(extra):
                padding = self.prefix_width - len(status) - len(extra) - 1
                padding = padding * " "
                suffix = f"{padding}{self.theme.extra(extra)}"
            else:
                suffix = ""
            self._cached_out = [f"{prefix}{status}{suffix}\n"]
            for ref in self._children:
                child = ref()
                if child.visible:
                    self._cached_out.extend(child._get_output(now))
            self._dirty = False
        return self._cached_out


class _TermManager:
    def __init__(self, min_update_freq=1, max_update_freq=12) -> None:
        self._streams: list[weakref.ReferenceType[TermStream]] = list()
        self._fp = sys.stdout
        # self._fp.reconfigure(write_through=False)
        self._min_delay = 1 / min_update_freq
        self._max_delay = 1 / max_update_freq
        self._up_ev = asyncio.Event()
        self._stop_requested = False
        self._raw_lines = list()
        self._thread = None
        self._flush_callbacks = list()

        global _manager
        if _manager is not None:
            raise RuntimeError("Only one _TermManager can be created")

        match mode:
            case TerminalMode.CODE:
                self._flush = self._flush_code
            case _:
                self._flush = self._flush_sticky

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
        try:
            loop = asyncio.get_running_loop()
            self._thread = asyncio.create_task(self._render(), name="terminal-rendering")
        except RuntimeError:
            pass

    def stop(self):
        if self._thread is not None:
            self._stop_requested = True
            self._up_ev.set()

    def update(self):
        self._up_ev.set()

    def write(self, s: str, end: str = "\n"):
        self._raw_lines.append(s + end)
        self.update()

    ts = TermSequence

    def _flush_sticky(self, prev_line_count):
        out = self._fp
        self._up_ev.clear()
        stop = self._stop_requested
        now = time.time()
        output_lines = []
        if prev_line_count:
            output_lines.append(self.ts.prev(prev_line_count))
        prev_line_count = 0
        force = len(self._raw_lines)
        max_height = self.height - 2

        status_lines = []
        if mode == TerminalMode.STICKY:
            for ref in self._streams:
                stream = ref()
                if stream is None:
                    continue
                is_dirty, is_visible = stream._refresh_state()
                if is_dirty or force:
                    prev_height = len(stream._cached_out)
                    status_lines.append(self.ts.line_clear())
                    data = stream._get_output(now)
                    height = len(data)
                    if prev_line_count + height > max_height:
                        break

                    if is_visible:
                        if prev_height != height:
                            force = True  # force re-render next streams
                        status_lines.extend(data)
                        prev_line_count += height
                    elif prev_height != 1:
                        force = True
                elif is_visible:
                    # just jump over
                    height = len(stream._cached_out)
                    if prev_line_count + height > max_height:
                        break

                    prev_line_count += height
                    status_lines.append(self.ts.next(height))

            # insert separator
            if prev_line_count:
                status_lines.insert(0, "―" * (self.width) + "\n")
                prev_line_count += 1

        if self._raw_lines:
            lines = []
            line_count = 0
            for ls in self._raw_lines:
                nls = [l.rstrip() + "\n" for l in ls.splitlines()]
                line_count += len(nls)
                for l in nls:
                    line_count += len(l) // self.width
                lines.extend(nls)
            if mode == TerminalMode.STICKY:
                output_lines.append(self.ts.sreen_clear(0))
                if line_count + prev_line_count > max_height:
                    output_lines.append(
                        self.ts.scroll_up(prev_line_count)
                        + self.ts.prev(prev_line_count)
                    )
            output_lines.extend(lines)

            self._raw_lines = list()

        if mode == TerminalMode.STICKY:
            # clear rest of the screen
            status_lines.append(self.ts.sreen_clear(0))

        # for line in [*output_lines, *status_lines]:
        #     out.write(line)
        #     out.flush()
        out.writelines([*output_lines, *status_lines])
        out.flush()
        
        for callback in self._flush_callbacks:
            callback()
        self._flush_callbacks = list()

        return stop, prev_line_count
    
    def _flush_code(self, prev_line_count):
        out = self._fp
        self._up_ev.clear()
        stop = self._stop_requested
        now = time.time()
        if self._raw_lines:
            out.writelines(self._raw_lines)
            self._raw_lines = []
        for ref in self._streams:
            stream = ref()
            if stream is None:
                continue
            is_dirty, is_visible = stream._refresh_state()
            if is_dirty and is_visible:
                data = stream._get_output(now)
                out.writelines(data)
        
        for callback in self._flush_callbacks:
            callback()
        self._flush_callbacks = list()
            
        return stop, 0

    async def _render(self):
        out = self._fp
        if mode == TerminalMode.STICKY:
            out.write(self.ts.home() + self.ts.sreen_clear())
        prev_line_count = 0
        stop = False
        last_update = 0

        async def auto_refresh():
            await asyncio.sleep(self._min_delay)
            self.update()

        auto_refresh_task = asyncio.create_task(auto_refresh())
        with self.ts.hidden_cursor() if mode == TerminalMode.STICKY else nullcontext():
        # with nullcontext():
            while not stop:
                await self._up_ev.wait()
                now = time.time()
                delay = now - last_update
                if delay < self._max_delay and not self._stop_requested:
                    await asyncio.sleep(self._max_delay - delay)
                stop, prev_line_count = self._flush(prev_line_count)
                last_update = time.time()

            auto_refresh_task.cancel()

            self._up_ev.set()
            while self._up_ev.is_set():
                _, prev_line_count = self._flush(prev_line_count)
                await asyncio.sleep(0)

        self._thread = None


_manager: _TermManager = None


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


def write(s: str, end="\n"):
    return manager().write(s, end)
