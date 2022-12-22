import re


class Version:
    version_pattern = re.compile('[.-]')

    def __init__(self, *args) -> None:
        if len(args) == 1 and isinstance(args[0], str):
            args = Version.version_pattern.split(args[0])
        else:
            args = list(args)
        it = iter(args)
        self.major = int(next(it))
        tmp = next(it, None)
        self.minor = int(tmp) if tmp is not None else None
        tmp = next(it, None)
        self.patch = int(tmp) if tmp is not None else None
        tmp = next(it, None)
        self.build = int(tmp) if tmp is not None else None

    def __eq__(self, other: 'Version'):
        return self.major == other.major \
            and self.minor == other.minor \
            and self.patch == other.patch \
            and self.build == other.build

    def __ge__(self, other: 'Version'):
        return self.major >= other.major \
            or self.minor >= other.minor \
            or self.patch >= other.patch \
            or self.build >= other.build
    
    def __lt__(self, other: 'Version'):
        return self.major < other.major \
            or self.minor < other.minor \
            or self.patch < other.patch \
            or self.build < other.build

    def __str__(self) -> str:
        res = str(self.major)
        if self.minor is not None:
            res += f'.{self.minor}'
            if self.patch is not None:
                res += f'.{self.patch}'
                if self.build is not None:
                    res += f'.{self.build}'
        return res
    
