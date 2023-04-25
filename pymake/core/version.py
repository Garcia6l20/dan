import re


class Version:
    version_pattern = re.compile('[.-]')

    def __init__(self, *args) -> None:
        if len(args) == 1 and isinstance(args[0], str):
            args = Version.version_pattern.split(args[0])
        else:
            args = list(args)
        self._parts = tuple(int(a) for a in args)

    @property
    def major(self):
        return self._parts[0]

    @property
    def minor(self):
        if len(self._parts) > 1:
            return self._parts[1]

    @property
    def patch(self):
        if len(self._parts) > 2:
            return self._parts[2]
        
    @property
    def build(self):
        if len(self._parts) > 3:
            return self._parts[3]

    def __eq__(self, other):
        if isinstance(other, str):
            other = Version(other)
        elif not isinstance(other, Version):
            return False
        return self.major == other.major \
            and (self.minor or 0) == (other.minor or 0) \
            and (self.patch or 0) == (other.patch or 0) \
            and (self.build or 0) == (other.build or 0)

    def __gt__(self, other: 'Version'):
        if isinstance(other, str):
            other = Version(other)
        elif not isinstance(other, Version):
            return False
        return self.major >= other.major \
            or (self.minor or 0) > (other.minor or 0) \
            or (self.patch or 0) > (other.patch or 0) \
            or (self.build or 0) > (other.build or 0)

    def __ge__(self, other: 'Version'):
        if isinstance(other, str):
            other = Version(other)
        elif not isinstance(other, Version):
            return False
        return self.major >= other.major \
            or (self.minor or 0) >= (other.minor or 0) \
            or (self.patch or 0) >= (other.patch or 0) \
            or (self.build or 0) >= (other.build or 0)
    
    def __lt__(self, other: 'Version'):
        if isinstance(other, str):
            other = Version(other)
        elif not isinstance(other, Version):
            return False
        return self.major < other.major \
            or (self.minor or 0) < (other.minor or 0) \
            or (self.patch or 0) < (other.patch or 0) \
            or (self.build or 0) < (other.build or 0)
    
    def __le__(self, other: 'Version'):
        if isinstance(other, str):
            other = Version(other)
        elif not isinstance(other, Version):
            return False
        return self.major < other.major \
            or (self.minor or 0) <= (other.minor or 0) \
            or (self.patch or 0) <= (other.patch or 0) \
            or (self.build or 0) <= (other.build or 0)

    def __str__(self) -> str:
        res = str(self.major)
        if self.minor is not None:
            res += f'.{self.minor}'
            if self.patch is not None:
                res += f'.{self.patch}'
                if self.build is not None:
                    res += f'.{self.build}'
        return res

