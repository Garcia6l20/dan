#!/usr/bin/env python3

from pymake import cli
from pymake.cxx import Library, Executable
from pymake.pkgconfig import Package
from copy import deepcopy

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

import os
from pathlib import Path
import re

def find_file(expr, paths) -> tuple[Path, Path]:
    r = re.compile(expr)
    for path in paths:
        for root, _, files in os.walk(os.path.expandvars(os.path.expanduser(path))):
            for file in files:
                if r.match(file):
                    return Path(root), file
    return None, None

def find_include_path(name, paths = list()) -> Path:
    root, file = find_file(name, [*paths, *include_paths_lookup])
    if root:
        return root / file

def find_library(name, paths = list()) -> Path:
    if os.name == 'posix':
        expr = fr'lib{name}\.(so|a)'
    elif os.name == 'nt':
        expr = fr'lib{name}\.(lib|dll)'
    root, file = find_file(expr, [*paths, *library_paths_lookup])
    if root:
        return root / file

def find_pkg_config(name, paths = list()) -> Path:
    root, file = find_file(fr'.*{name}\.pc', [*paths, *library_paths_lookup])
    if root:
        return root / file

path = find_pkg_config('spdlog', ['~/.conan/data'])

class PkgConfig:
    def __init__(self, config, search_paths: list[str] = list()) -> None:
        self.config_path = config
        self.search_paths = search_paths
        self.vars = dict()
        self.sections = dict()
        with open(config) as f:
            lines = [l for l in [l.strip().removesuffix('\n') for l in f.readlines()] if len(l)]
            for line in lines:
                pos = line.find(':')
                m = re.match('(.+)(:|=)(.+)', line)
                if m and m.group(2) == '=':
                    self.vars[m.group(1).strip()] = m.group(3).strip()
                elif m:
                    self.sections[m.group(1).strip().lower()] = m.group(3).strip()

    def __substitute(self, item):
        for var in self.vars:
            pass

    @property
    def cflags(self):
        pass


conf = PkgConfig(path)
print(conf.__dict__)
import sys
sys.exit(0)


print(path)
os.environ['PKG_CONFIG_PATH'] = str(path.parent)
print(os.environ['PKG_CONFIG_PATH'])
spdlog = Package('spdlog', pc_file=path)

import pkgconfig
print(pkgconfig.list_all())

print(find_include_path('spdlog.h', ['~/.conan/data']))
print(find_library('spdlog', ['~/.conan/data']))
print(find_pkg_config('spdlog', ['~/.conan/data']))

class Pkg:
    def __init__(self) -> None:
        pass


imported = Executable(sources=['main.cpp'])

if __name__ == '__main__':
    cli()
