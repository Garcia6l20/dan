import os
import pathlib

Path = type(pathlib.Path())

@property
def modification_time(self):
    return self.stat().st_mtime

Path.modification_time = modification_time


def younger_than(self, other):
    time = other if isinstance(other, float) else other.modification_time
    assert isinstance(time, float)
    return self.modification_time > time

Path.younger_than = younger_than


def older_than(self, other):
    time = other if isinstance(other, float) else other.modification_time
    assert isinstance(time, float)
    return self.modification_time < time

Path.older_than = older_than


def utime(self, *args, **kw_args):
    os.utime(self, *args, **kw_args)

Path.utime = utime

@property
def is_empty(self):
    if os.path.exists(self) and not os.path.isfile(self):

        # Checking if the directory is empty or not
        if not os.listdir(self):
            return True
        else:
            return False
    else:
        return False

Path.is_empty = is_empty
