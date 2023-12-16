from asyncio import *
from async_property import *

import threading
import concurrent.futures
import multiprocessing
import typing as t
import inspect
import threading

from dan.core.functools import BaseDecorator


async def may_await(obj):
    """Awaits given object if it is an awaitable

    If obj is an awaitable it's await-result is returned.
    If obj is not an awaitable it is returned directly.
    """
    if inspect.isawaitable(obj):
        return await obj
    else:
        return obj


class Cached(BaseDecorator):
    def __init__(self, fn, unique=False):
        self.__fn = fn
        self.__unique = unique
        self.__is_method = fn.__call__.__class__.__name__ == "method-wrapper"
        if not self.__is_method and self.__unique:
            self.__cache = None
        else:
            self.__cache: dict[int, Future] = dict()

    async def __call__(self, *args, **kwds):
        if not self.__is_method and self.__unique:
            if self.__cache is None:
                self.__cache = Future()
                try:
                    self.__cache.set_result(await self.__fn(*args, **kwds))
                except Exception as ex:
                    self.__cache.set_exception(ex)
            elif not self.__cache.done():
                await self.__cache
            return self.__cache.result()
        else:
            key = id(args[0]) if self.__unique else hash((args, frozenset(kwds)))
            if key not in self.__cache:
                self.__cache[key] = Future()
                try:
                    self.__cache[key].set_result(await self.__fn(*args, **kwds))
                except Exception as ex:
                    self.__cache[key].set_exception(ex)
            elif not self.__cache[key].done():
                await self.__cache[key]

            return self.__cache[key].result()

    def clear_all(self):
        if self.__unique:
            self.__cache = dict()
        else:
            self.__cache = None


def cached(*args, **kwargs):
    if len(args) == 1 and callable(args[0]):
        return Cached(args[0])
    else:

        def wrapper(fn):
            return Cached(fn, *args, **kwargs)

        return wrapper


class _SyncWaitThread(threading.Thread):
    def __init__(self, coro):
        self.coro = coro
        self.result = None
        self.err = None
        super().__init__()

    def run(self):
        try:
            loop = new_event_loop()
            self.result = loop.run_until_complete(self.coro)
            tasks = all_tasks(loop)
            if len(tasks):
                for t in tasks:
                    t.cancel()
                loop.run_until_complete(wait(tasks))
        except Exception as err:
            self.err = err


def sync_wait(coro):
    thread = _SyncWaitThread(coro)
    thread.start()
    thread.join()
    if thread.err:
        raise thread.err
    return thread.result


_async_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=multiprocessing.cpu_count(),
)


async def async_wait(fn, *args, **kwargs):
    loop = get_running_loop()

    def wrapper():
        return fn(*args, **kwargs)

    return await loop.run_in_executor(_async_pool, wrapper)


class ExceptionGroup(Exception):
    def __init__(self, message: str, errors: t.Iterable[Exception] = set()) -> None:
        super().__init__(message)
        self.errors: set[Exception] = set(errors)

    def add(self, e: Exception):
        self.errors.add(e)

    def __str__(self) -> str:
        s = super().__str__()
        for e in self.errors:
            s += "\n" + str(e)
        return s


class TaskGroup:
    """Asynchronous context manager for managing groups of tasks.

    Example use:

        async with asyncio.TaskGroup('my group name') as group:
            task1 = group.create_task(some_coroutine(...))
            task2 = group.create_task(other_coroutine(...))
        print("Both tasks have completed now.")

    All tasks are awaited when the context manager exits.

    Any exceptions other than `asyncio.CancelledError` raised within
    a task will cancel all remaining tasks and wait for them to exit.
    The exceptions are then combined and raised as an `ExceptionGroup`.
    """

    def __init__(self, name="a TaskGroup"):
        self._entered = False
        self._exiting = False
        self._aborting = False
        self._loop = None
        self._parent_task = None
        self._parent_cancel_requested = False
        self._tasks: set[Task] = set()
        self._errors = []
        self._results = []
        self._base_error = None
        self._on_completed_fut = None
        self._name = name

    def __repr__(self):
        info = [""]
        if self._tasks:
            info.append(f"tasks={len(self._tasks)}")
        if self._errors:
            info.append(f"errors={len(self._errors)}")
        if self._aborting:
            info.append("cancelling")
        elif self._entered:
            info.append("entered")

        info_str = " ".join(info)
        return f"<TaskGroup{info_str}>"

    async def __aenter__(self):
        if self._entered:
            raise RuntimeError(f"TaskGroup {self!r} has been already entered")
        self._entered = True

        if self._loop is None:
            self._loop = get_running_loop()

        self._parent_task = current_task(self._loop)
        if self._parent_task is None:
            raise RuntimeError(f"TaskGroup {self!r} cannot determine the parent task")

        return self

    async def __aexit__(self, et, exc, tb):
        self._exiting = True

        if exc is not None and self._is_base_error(exc) and self._base_error is None:
            self._base_error = exc

        propagate_cancellation_error = exc if et is CancelledError else None
        if self._parent_cancel_requested:
            # If this flag is set we *must* call uncancel().
            if self._parent_task.uncancel() == 0:
                # If there are no pending cancellations left,
                # don't propagate CancelledError.
                propagate_cancellation_error = None

        if et is not None:
            if not self._aborting:
                # Our parent task is being cancelled:
                #
                #    async with TaskGroup() as g:
                #        g.create_task(...)
                #        await ...  # <- CancelledError
                #
                # or there's an exception in "async with":
                #
                #    async with TaskGroup() as g:
                #        g.create_task(...)
                #        1 / 0
                #
                self._abort()

        # We use while-loop here because "self._on_completed_fut"
        # can be cancelled multiple times if our parent task
        # is being cancelled repeatedly (or even once, when
        # our own cancellation is already in progress)
        while self._tasks:
            if self._on_completed_fut is None:
                self._on_completed_fut = self._loop.create_future()
            try:
                await self._on_completed_fut
            except CancelledError as ex:
                if not self._aborting:
                    # Our parent task is being cancelled:
                    #
                    #    async def wrapper():
                    #        async with TaskGroup() as g:
                    #            g.create_task(foo)
                    #
                    # "wrapper" is being cancelled while "foo" is
                    # still running.
                    propagate_cancellation_error = ex
                    self._abort()

            self._on_completed_fut = None

        assert not self._tasks

        if self._base_error is not None:
            raise self._base_error

        # Propagate CancelledError if there is one, except if there
        # are other errors -- those have priority.
        if propagate_cancellation_error and not self._errors:
            raise propagate_cancellation_error

        if et is not None and et is not CancelledError:
            self._errors.append(exc)

        if self._errors:
            # Exceptions are heavy objects that can have object
            # cycles (bad for GC); let's not keep a reference to
            # a bunch of them.
            try:
                me = ExceptionGroup(f"unhandled errors in {self._name}", self._errors)
                raise me from None
            finally:
                self._errors = None

    def create_task(self, coro, *, name=None, context=None):
        """Create a new task in this group and return it.

        Similar to `asyncio.create_task`.
        """
        if not self._entered:
            raise RuntimeError(f"TaskGroup {self!r} has not been entered")
        if self._exiting and not self._tasks:
            raise RuntimeError(f"TaskGroup {self!r} is finished")
        if self._aborting:
            raise RuntimeError(f"TaskGroup {self!r} is shutting down")
        if isfuture(coro):
            task = coro
        elif context is None:
            task = self._loop.create_task(coro, name=name)
        else:
            task = self._loop.create_task(coro, context=context, name=name)
        task.add_done_callback(self._on_task_done)
        self._tasks.add(task)
        return task

    # Since Python 3.8 Tasks propagate all exceptions correctly,
    # except for KeyboardInterrupt and SystemExit which are
    # still considered special.

    def _is_base_error(self, exc: BaseException) -> bool:
        assert isinstance(exc, BaseException)
        return isinstance(exc, (SystemExit, KeyboardInterrupt))

    def _abort(self):
        self._aborting = True

        for t in self._tasks:
            if not t.done():
                t.cancel()

    def _on_task_done(self, task):
        self._tasks.discard(task)

        if self._on_completed_fut is not None and not self._tasks:
            if not self._on_completed_fut.done():
                self._on_completed_fut.set_result(True)

        if task.cancelled():
            return

        exc = task.exception()
        if exc is None:
            self._results.append(task.result())
            return

        self._errors.append(exc)
        if self._is_base_error(exc) and self._base_error is None:
            self._base_error = exc

        if self._parent_task.done():
            # Not sure if this case is possible, but we want to handle
            # it anyways.
            self._loop.call_exception_handler(
                {
                    "message": f"Task {task!r} has errored out but its parent "
                    f"task {self._parent_task} is already completed",
                    "exception": exc,
                    "task": task,
                }
            )
            return

        if not self._aborting and not self._parent_cancel_requested:
            # If parent task *is not* being cancelled, it means that we want
            # to manually cancel it to abort whatever is being run right now
            # in the TaskGroup.  But we want to mark parent task as
            # "not cancelled" later in __aexit__.  Example situation that
            # we need to handle:
            #
            #    async def foo():
            #        try:
            #            async with TaskGroup() as g:
            #                g.create_task(crash_soon())
            #                await something  # <- this needs to be canceled
            #                                 #    by the TaskGroup, e.g.
            #                                 #    foo() needs to be cancelled
            #        except Exception:
            #            # Ignore any exceptions raised in the TaskGroup
            #            pass
            #        await something_else     # this line has to be called
            #                                 # after TaskGroup is finished.
            self._abort()
            self._parent_cancel_requested = True
            self._parent_task.cancel()

    def results(self):
        if not self._entered:
            raise RuntimeError(f"TaskGroup {self!r} has not been entered")
        if self._exiting and self._tasks:
            raise RuntimeError(f"TaskGroup {self!r} is not finished")
        return self._results


class async_lock:
    def __init__(self, lock):
        self.lock = lock

    async def __aenter__(self):
        loop = get_event_loop()
        await loop.run_in_executor(_async_pool, self.lock.acquire)

    async def __aexit__(self, *args):
        self.lock.release()


class ThreadLock:
    def __init__(self) -> None:
        self._lk = threading.Lock()

    def __enter__(self):
        self._lk.acquire()

    def __exit__(self, *exc):
        self._lk.release()

    async def __aenter__(self):
        loop = get_event_loop()
        await loop.run_in_executor(_async_pool, self._lk.acquire)

    async def __aexit__(self, *exc):
        self._lk.release()


spawn = create_task
