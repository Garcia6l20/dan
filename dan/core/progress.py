import tqdm
from enum import Enum
from dan.core import asyncio


class ProgressMode(Enum):
    NONE = 0
    BASIC = 1
    IDENTIFIED = 2


mode = ProgressMode.BASIC


def set_progress_mode(new_mode: ProgressMode):
    global mode
    mode = new_mode


import math


class BarFormatter(str):
    def format(self, bar, ncols=1, total=None, elapsed_s=0.0, **format_dict):
        if total is None and ncols is not None:
            tmp = super().format(
                bar="{}",
                ncols=ncols,
                total=total,
                elapsed_s=elapsed_s,
                **format_dict,
            )
            cursor_width = ncols // 12
            bar_width = ncols - len(tmp) - (cursor_width - 2)
            pos = 0.5 + math.sin(math.pi * elapsed_s) / 2
            bar_length, _ = divmod(pos * bar_width, 1)
            bar = (
                " " * int(bar_length) + "\u2587" * cursor_width + " " * int(bar_width - bar_length)
            )
            return tmp.format(bar)
        return super().format(
            bar=bar, ncols=ncols, total=total, elapsed_s=elapsed_s, **format_dict
        )


class Bar(tqdm.tqdm):
    __uid_count = 1

    __doc__ = tqdm.tqdm.__doc__

    def __init__(self, desc, leave=False, total=None, disable=False, **kwargs):
        self._desc = None
        if kwargs.pop("root", False):
            self.__id = 0
            leave = True
        else:
            self.__id = self.__uid_count
            Bar.__uid_count += 1
        super().__init__(
            desc=desc,
            leave=leave,
            total=total,
            maxinterval=0.5,
            disable=disable or mode == ProgressMode.NONE,
            **kwargs,
        )
        self.bar_format = BarFormatter("{l_bar}{bar}{r_bar}")

    @property
    def desc(self):
        if mode == ProgressMode.IDENTIFIED:
            return f"{self.__id}-{self._desc}"
        else:
            return self._desc

    @desc.setter
    def desc(self, value):
        self._desc = value

    def close(self) -> None:
        if mode == ProgressMode.IDENTIFIED and (
            self.total == None or self.total != self.n
        ):
            # ensure a 100% is printed
            if self.n == 0:
                self.n = 1
            self.total = self.n
            self.n -= 1
            self.update()
            self.refresh()
        return super().close()

    def __call__(self, *args, **kwargs):
        super().update(*args, **kwargs)


class TaskGroup(asyncio.TaskGroup):
    def __init__(self, name="a TaskGroup", progress_options: dict = None):
        super().__init__(name)
        if progress_options is None:
            progress_options = dict()
        self._progress_options = progress_options

    def __notify_bar_task_done(self, task):
        self._bar.update()

    def __aexit__(self, et, exc, tb):
        total = len(self._tasks)
        if total:
            self._bar = Bar(
                self._name, total=len(self._tasks), **self._progress_options
            )
            for task in self._tasks:
                task.add_done_callback(self.__notify_bar_task_done)
            self._bar.refresh()
        return super().__aexit__(et, exc, tb)


async def _update_pbar(bar: Bar, update_delay=1):
    try:
        while True:
            bar.refresh()
            await asyncio.sleep(update_delay)
    except asyncio.CancelledError:
        pass


class BarProxy:
    def __init__(self, name: str):
        self.name = name
        self._bar: Bar = None
        self._stack = list()

    def __call__(self, desc: str, total=None, unit="it", **kwargs):
        desc = f"{self.name}: {desc}"
        if self._bar is None:
            self._bar = Bar(desc, total=total, unit=unit, **kwargs)
        else:
            self._stack.append(
                {
                    "desc": self._bar._desc,
                    "n": self._bar.n,
                    "total": self._bar.total,
                    "unit": self._bar.unit,
                    "last_print_n": self._bar.last_print_n,
                    "last_print_t": self._bar.last_print_t,
                }
            )
            self._bar.desc = desc
            self._bar.unit = unit
            self._bar.reset(total)
        return self

    def __enter__(self):
        return self._bar.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        if len(self._stack):
            prev = self._stack.pop()
            self._bar.desc = prev["desc"]
            self._bar.n = prev["n"]
            self._bar.total = prev["total"]
            self._bar.unit = prev["unit"]
            self._bar.last_print_n = prev["last_print_n"]
            self._bar.last_print_t = prev["last_print_t"]
            self._bar.refresh()
        else:
            self._bar.__exit__(exc_type, exc_value, traceback)


async def async_wait(desc, fn, *args, **kwargs):
    with Bar(desc) as bar:
        done, pending = await asyncio.wait(
            [
                asyncio.create_task(asyncio.async_wait(fn, *args, **kwargs)),
                asyncio.create_task(_update_pbar(bar)),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for pending in pending:
            pending.cancel()
        return list(done)[0].result
