import tqdm
from enum import Enum

class ProgressMode(Enum):
    NONE = 0
    BASIC = 1
    IDENTIFIED = 2

mode = ProgressMode.BASIC

def set_progress_mode(new_mode: ProgressMode):
    global mode
    mode = new_mode

class progress(tqdm.tqdm):

    __uid_count = 1

    __doc__ = tqdm.tqdm.__doc__
    def __init__(self, *args, **kwargs):
        if kwargs.pop("root", False):
            self.__id = 0
        else:
            self.__id = self.__uid_count
            progress.__uid_count += 1
        desc = kwargs.pop("desc", "")
        if mode == ProgressMode.IDENTIFIED:
            desc = f'{self.__id}-{desc}'
        super().__init__(*args, desc=desc, **kwargs)
        self.disable = mode == ProgressMode.NONE
    
    def set_description(self, desc="", refresh=True):
        if mode == ProgressMode.IDENTIFIED:
            desc = f'{self.__id}-{desc}'
        super().set_description(desc, refresh)

    def set_description_str(self, desc="", refresh=True):
        if mode == ProgressMode.IDENTIFIED:
            desc = f'{self.__id}-{desc}'
        super().set_description(desc, refresh)
    
    def close(self) -> None:
        if mode == ProgressMode.IDENTIFIED and self.total == None:
            # ensure a 100% is printed
            self.total = self.n
            self.n -= 1
            self.update()
            self.refresh()
        return super().close()

    def __call__(self, *args, **kwargs):
        super().update(*args, **kwargs)

progress.__init__.__doc__ = tqdm.tqdm.__init__.__doc__
