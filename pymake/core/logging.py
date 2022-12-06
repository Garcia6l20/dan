import logging

import colorama

if hasattr(colorama, 'just_fix_windows_console'):
    colorama.just_fix_windows_console()


class ColoredFormatter(logging.Formatter):

    COLORS = {
        'WARNING': colorama.Fore.YELLOW,
        'INFO': colorama.Fore.GREEN,
        'DEBUG': colorama.Fore.BLUE,
        'CRITICAL': colorama.Fore.YELLOW,
        'ERROR': colorama.Fore.RED
    }

    COLOR_FORMAT = \
        f"[{colorama.Style.DIM}%(asctime)s.%(msecs)03d{colorama.Style.RESET_ALL}]" \
        f"[%(levelname)s][{colorama.Style.BRIGHT}%(name)s{colorama.Style.RESET_ALL}]: %(message)s "\
        f"({colorama.Style.DIM}%(filename)s:%(lineno)d{colorama.Style.RESET_ALL})"
    
    FORMAT = \
        "[%(asctime)s.%(msecs)03d]" \
        "[%(levelname)s][%(name)s]: %(message)s "\
        "(%(filename)s:%(lineno)d)"

    def __init__(self, use_color=True):
        super().__init__(self.COLOR_FORMAT if use_color else self.FORMAT, datefmt='%H:%M:%S')
        self.use_color = use_color

    def format(self, record):
        levelname = record.levelname
        if self.use_color and levelname in self.COLORS:
            record.levelname = colorama.Style.BRIGHT + \
                self.COLORS[levelname] + levelname + colorama.Style.RESET_ALL
            record.msg = colorama.Style.NORMAL + \
                self.COLORS[levelname] + record.msg + colorama.Style.RESET_ALL
        return super().format(record)


class ColoredLogger(logging.Logger):

    def __init__(self, name):
        super().__init__(name)

        color_formatter = ColoredFormatter()
        if not self.hasHandlers():
            console = logging.StreamHandler()
            console.setFormatter(color_formatter)
            self.addHandler(console)
        else:
            for handler in self.handlers:
                handler.setFormatter(color_formatter)


logging.setLoggerClass(ColoredLogger)
# logging.basicConfig(level=logging.INFO)


class Logging:
    def __init__(self, name: str = None) -> None:
        if name is None:
            name = self.__class__.__name__
        self.logger = logging.getLogger(name)
        self.debug = self.logger.debug
        self.info = self.logger.info
        self.warn = self.logger.warn
        self.error = self.logger.error
