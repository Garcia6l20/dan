import re


class Version:
    version_pattern = re.compile(r'[\.-]')

    def __init__(self, *args) -> None:
        if len(args) == 1 and isinstance(args[0], str):
            parts = Version.version_pattern.split(args[0])
            args = list()
            # cleanup
            for a in parts:
                # drop non numeric parts (ie.: v0.11.0 -> 0.11.0, 1.2-preview5, mylib-3.2, etc...)
                while not a.isnumeric() and len(a):
                    a = a[1:]
                if len(a):
                    args.append(a)
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
        if self.major != other.major:
            return False
        if self.minor != other.minor:
            return False
        if self.patch != other.patch:
            return False
        if self.build != other.build:
            return False
        return True
    
    def is_compatible(self, other):
        if isinstance(other, str):
            other = Version(other)
        elif not isinstance(other, Version):
            return False
        if self.major != other.major:
            return False
        if self.minor and other.minor and self.minor != other.minor:
            return False
        if self.patch and other.patch and self.patch != other.patch:
            return False
        if self.build and other.build and self.build != other.build:
            return False
        return True

    def __gt__(self, other: 'Version'):
        if isinstance(other, str):
            other = Version(other)
        elif not isinstance(other, Version):
            return False
        for mine, their in zip(self._parts, other._parts):
            if mine > their:
                return True
            if mine < their:
                return False
        return True


    def __ge__(self, other: 'Version'):
        if isinstance(other, str):
            other = Version(other)
        elif not isinstance(other, Version):
            return False
        for mine, their in zip(self._parts, other._parts):
            if mine >= their:
                return True
            if mine < their:
                return False
        return False
    
    def __lt__(self, other: 'Version'):
        if isinstance(other, str):
            other = Version(other)
        elif not isinstance(other, Version):
            return False
        for mine, their in zip(self._parts, other._parts):
            if mine < their:
                return True
            if mine > their:
                return False
        return False

    
    def __le__(self, other: 'Version'):
        if isinstance(other, str):
            other = Version(other)
        elif not isinstance(other, Version):
            return False
        for mine, their in zip(self._parts, other._parts):
            if mine < their:
                return True
            if mine > their:
                return False
        return True

    def __str__(self) -> str:
        res = str(self.major)
        if self.minor is not None:
            res += f'.{self.minor}'
            if self.patch is not None:
                res += f'.{self.patch}'
                if self.build is not None:
                    res += f'.{self.build}'
        return res
    
    def __repr__(self) -> str:
        return f'Version[{self}]'
    
    def __hash__(self) -> int:
        h = 0
        for part in self._parts:
            h ^= hash(part)
        return h


class VersionSpec:

    @staticmethod
    def parse(data: str) -> tuple[str|None, 'VersionSpec']:
        m = re.match(r'(.+?)?\s+?([><]=?|=)\s+([\d\.]+)', data)
        if m:
            name = m[1]
            op = m[2]
            version = Version(m[3])
            return name, VersionSpec(version, op)
        return None, None


    def __init__(self, version: Version, op: str) -> None:
        self.version = version
        self.op = op
        
    def is_compatible(self, version: Version):
        match self.op:
            case '==':
                return version == self.version
            case '=':
                return version.is_compatible(self.version)
            case '>':
                return version > self.version
            case '>=':
                return version >= self.version
            case '<':
                return version < self.version
            case '<=':
                return version <= self.version
            case _:
                return False
            
    def __str__(self) -> str:
        return f'{self.op} {self.version}'
