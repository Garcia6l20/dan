import logging


class Logging:
    def __init__(self, name : str = None) -> None:
        if name is None:
            name = self.__class__.__name__
        self.logger = logging.getLogger(name)
        self.debug = self.logger.debug
        self.info = self.logger.info
        self.warn = self.logger.warn
        self.error = self.logger.error
