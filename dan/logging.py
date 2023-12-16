from logging import *
from termcolor import colored
from dan.core.terminal import TermLogHandler

# default level
getLogger().setLevel(INFO)


def merge(lhs, rhs):
    if type(lhs) != type(rhs):
        raise RuntimeError(f"cannot merge {type(lhs)} with {rhs}")
    if type(lhs) == dict:
        for k in rhs:
            if k in lhs:
                lhs[k] = merge(lhs[k], rhs[k])
            else:
                lhs[k] = rhs[k]
    elif type(lhs) == list:
        lhs.extend(rhs)
    return lhs


class bind_back:
    def __init__(self, fn, *args):
        self.fn = fn
        self.args = args

    def __call__(self, *args, **kwds):
        return self.fn(*args, *self.args, **kwds)


class ColoredFormatter(Formatter):
    COLORS = {
        "WARNING": bind_back(colored, "yellow"),
        "INFO": bind_back(colored, "green"),
        "DEBUG": bind_back(colored, "cyan"),
        "CRITICAL": bind_back(colored, "yellow"),
        "ERROR": bind_back(colored, "red"),
    }

    COLORS_ATTRS = {
        "WARNING": list(),
        "INFO": list(),
        "DEBUG": list(),
        "CRITICAL": ["blink"],
        "ERROR": ["blink"],
    }

    COLOR_FORMAT = (
        f"[{colored('%(asctime)s.%(msecs)03d', 'grey')}]"
        f"[%(levelname)s] {colored('%(name)s:', 'white', attrs=['bold'])} %(message)s "
    )  # \
    # f"({colored('%(filename)s:%(lineno)d', 'grey')})"

    FORMAT = "[%(asctime)s.%(msecs)03d]" "[%(levelname)s] %(name)s: %(message)s "  # \
    # "(%(filename)s:%(lineno)d)"

    def __init__(self, use_color=True):
        super().__init__(
            self.COLOR_FORMAT if use_color else self.FORMAT, datefmt="%H:%M:%S"
        )
        self.use_color = use_color

    def format(self, record):
        levelname = record.levelname
        if self.use_color and levelname in self.COLORS:
            record.levelname = self.COLORS[levelname](
                levelname, attrs=["bold", *self.COLORS_ATTRS[levelname]]
            )
            record.msg = self.COLORS[levelname](record.msg, attrs=[])
        return super().format(record)


_color_formatter = ColoredFormatter()
_no_color_formatter = ColoredFormatter(use_color=False)


def setup_logger(logger: Logger):
    if not logger.hasHandlers():
        console = TermLogHandler()
        console.setFormatter(_color_formatter)
        logger.addHandler(console)
    else:
        for handler in logger.handlers:
            handler.setFormatter(
                _color_formatter
                if isinstance(handler, StreamHandler)
                else _no_color_formatter
            )


TRACE = DEBUG - 5
addLevelName(TRACE, "TRACE")

STATUS = INFO - 1
addLevelName(STATUS, "STATUS")

PROGRESS = INFO + 1
addLevelName(PROGRESS, "PROGRESS")


class ColoredLogger(Logger):
    def __init__(self, name):
        super().__init__(name)
        self.propagate = False
        setup_logger(self)

    def trace(self, message, *args, **kwargs):
        if self.isEnabledFor(TRACE):
            self._log(TRACE, message, args, **kwargs)


setLoggerClass(ColoredLogger)


class Logging:
    def get_logger(self, name=None):
        logger = getattr(self, "_logger", None)
        if logger is None:
            if name is None:
                name = getattr(self, "fullname", self.__class__.__name__)
            if name.startswith("root."):
                name = name.removeprefix("root.")
            logger = getLogger(name)
            setattr(self, "_logger", logger)
        return logger

    def trace(self, msg, *args, **kwargs):
        self.get_logger().trace(msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self.get_logger().debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.get_logger().info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.get_logger().warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.get_logger().error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self.get_logger().critical(msg, *args, **kwargs)


def _get_makefile_logger():
    from dan.core.include import context

    if not hasattr(context.current, "_logger"):
        makefile_logger = getLogger(context.current.name)
        setup_logger(makefile_logger)
        setattr(context.current, "_logger", makefile_logger)
    else:
        makefile_logger: Logger = getattr(context.current, "_logger")
    return makefile_logger


def trace(*args, **kwds):
    return _get_makefile_logger().trace(*args, **kwds)


def debug(*args, **kwds):
    return _get_makefile_logger().debug(*args, **kwds)


def info(*args, **kwds):
    return _get_makefile_logger().info(*args, **kwds)


def warning(*args, **kwds):
    return _get_makefile_logger().warning(*args, **kwds)


def error(*args, **kwds):
    return _get_makefile_logger().error(*args, **kwds)


def critical(*args, **kwds):
    return _get_makefile_logger().critical(*args, **kwds)


class lazy_fmt:
    def __init__(self, fn):
        self.__fn = fn

    def __str__(self):
        return self.__fn()
