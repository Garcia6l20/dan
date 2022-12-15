import os
import pathlib

class Path(type(pathlib.Path())):

    @property
    def modification_time(self):
        return self.stat().st_mtime

    def younger_than(self, other):
        time = other if isinstance(other, float) else other.modification_time
        assert isinstance(time, float)
        return self.modification_time > time

    def older_than(self, other):
        return not self.younger_than(other)

    def utime(self, *args, **kw_args):
        os.utime(self, *args, **kw_args)
