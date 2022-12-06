
import os
from pathlib import Path
import re

include_paths_lookup = [
    '~/.local/include',
    '/usr/local/include',
    '/usr/include',
]

programs_paths_lookup = [
    '~/.local/bin',
    '/usr/local/bin',
    '/usr/bin',
]

library_paths_lookup = [
    '$LD_LIBRARY_PATH'
    '~/.local/lib',
    '~/.local/lib64',
    '/usr/local/lib',
    '/usr/local/lib64',
    '/usr/lib',
    '/usr/lib/lib64',
    '/lib',
    '/lib64',
]


def find_file(expr, paths) -> tuple[Path, Path]:
    r = re.compile(expr)
    for path in paths:
        for root, _, files in os.walk(os.path.expandvars(os.path.expanduser(path))):
            for file in files:
                if r.match(file):
                    return Path(root), file
    return None, None


def find_include_path(name, paths=list()) -> Path:
    root, file = find_file(name, [*paths, *include_paths_lookup])
    if root:
        return root / file


def find_library(name, paths=list()) -> Path:
    if os.name == 'posix':
        expr = fr'lib{name}\.(so|a)'
    elif os.name == 'nt':
        expr = fr'lib{name}\.(lib|dll)'
    root, file = find_file(expr, [*paths, *library_paths_lookup])
    if root:
        return root / file
