
import os
from dan.core.pathlib import Path
import re

include_paths_lookup = [
    '~/.local/include',
    '/usr/local/include',
    '/usr/include',
]

programs_paths_lookup = os.getenv('PATH', '').split(os.pathsep)

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


def find_file(expr, paths) -> Path:
    r = re.compile(expr)
    for path in paths:
        for root, _, files in os.walk(os.path.expandvars(os.path.expanduser(path))):
            for file in files:
                if r.match(file):
                    return Path(root) / file

def find_files(expr, paths) -> list[Path]:
    r = re.compile(expr)
    files = list()
    for path in paths:
        for root, _, _files in os.walk(os.path.expandvars(os.path.expanduser(path))):
            for file in _files:
                if r.match(file):
                    files.append(Path(root) / file)
    return files


def find_include_path(name, paths=list()) -> Path:
    return find_file(name, [*paths, *include_paths_lookup])


def find_library(name, paths=list()) -> Path:
    if os.name == 'posix':
        expr = fr'lib{name}\.(so|a)'
    elif os.name == 'nt':
        expr = fr'lib{name}\.(lib|dll)'
    return find_file(expr, [*paths, *library_paths_lookup])

def find_executable(name, paths=list(), default_paths=True) -> Path:
    if os.name == 'posix':
        expr = name + '$'
    elif os.name == 'nt':
        expr = f'{name}.exe$'
    if default_paths:
        paths.extend(programs_paths_lookup)
    return find_file(expr, paths)

def find_executables(name, paths=list(), default_paths=True) -> list[Path]:
    if os.name == 'posix':
        expr = name + '$'
    elif os.name == 'nt':
        expr = f'{name}.exe$'
    if default_paths:
        paths.extend(programs_paths_lookup)
    return find_files(expr, paths)
