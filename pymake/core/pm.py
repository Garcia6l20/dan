
import re
from typing import Callable


class ReMatch:
    """Regular expression pattern matchin implementation
    """

    def __init__(self, s: str, fn: Callable[[re.Pattern, str], re.Match]) -> None:
        self._s = s
        self._fn = fn
        self._m = re.Match = None

    __match_args__ = ('_s', '_m')

    def __eq__(self, pattern: str | re.Pattern | tuple[str, int | re.RegexFlag]):
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        elif isinstance(pattern, tuple):
            pattern = re.compile(*pattern)
        self._m = self._fn(pattern, self._s)
        return self._m is not None
    
    def __str__(self) -> str:
        return self._s

    def __getitem__(
        self,
        group: int | str | tuple[int, ...] | tuple[str, ...]
    ) -> str | tuple[str, ...] | None:
        return self._m[group]

def re_search(string: str) -> ReMatch:
  return ReMatch(string, re.search)


def re_match(string: str) -> ReMatch:
  return ReMatch(string, re.match)


def re_fullmatch(string: str) -> ReMatch:
  return ReMatch(string, re.fullmatch)
