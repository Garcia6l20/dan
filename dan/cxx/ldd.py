from pathlib import Path
from dan.cxx import Executable
from dan.core import asyncio

import os
import pefile

def find_file_ignore_case(dirname, filename):
    if not os.path.exists(dirname):
        return None
    (root, _, filenames) = next(os.walk(dirname))
    filename_lower = filename.lower()
    for f in filenames:
        if f.lower() == filename_lower:
            return os.path.join(root, f)
    return None


def get_pe_deps(pe_data):
    deps = []
    if hasattr(pe_data, 'DIRECTORY_ENTRY_IMPORT'):
        for imp in pe_data.DIRECTORY_ENTRY_IMPORT:
            deps.append(imp.dll.decode())
    return deps


def find_dll(dll, dll_lookup_dirs, arch):
    for dir in dll_lookup_dirs:
        dll_path = find_file_ignore_case(dir, dll)
        if not dll_path:
            continue
        pe_data = pefile.PE(dll_path)
        if pe_data.FILE_HEADER.Machine == arch:
            return (dll, dll_path, get_pe_deps(pe_data))
    return (dll, None, None)


async def dep_tree(pe, dll_lookup_dirs, disable_multiprocessing = False):
    dlls = {} # stores all dlls we encounter, specifically {(basename(dll)).lower(): abspath(dll)}
    deps = {} # stores pe -> [dll] relations, specifically {abspath(pe): [basename(pe's direct dll dep)]}
    pe_data = pefile.PE(pe)
    arch = pe_data.FILE_HEADER.Machine

    async def _dep_tree(pe, pe_deps):
        pe = os.path.abspath(pe)
        if pe in deps:
            # aleady processed before
            return
        deps[pe] = pe_deps
        results = []
        # pefile.PE() takes very long time to run, so use multiprocessing to speed it up        
        async with asyncio.TaskGroup() as group:
            for dll in pe_deps:
                if dll.lower() not in dlls:
                    group.create_task(asyncio.async_wait(find_dll, dll, dll_lookup_dirs, arch))

        results = group.results()
        for dll, dll_path, _deps in results:
            # store the found dll
            if dll_path:
                dlls[dll.lower()] = dll_path
            # note that the dll wasn't found, so that we don't try to look for it again
            else:
                dlls[dll.lower()] = None
        # recursively process newly found dlls
        async with asyncio.TaskGroup() as group:
            for dll, dll_path, dll_deps in results:
                if dll_path:
                    await _dep_tree(dll_path, dll_deps)

    await _dep_tree(pe, get_pe_deps(pe_data))
    return (dlls, deps)

async def get_runtime_dependencies(t : Executable):
    dll_lookup_dirs = t.env['PATH'].split(os.pathsep)
    return await dep_tree(t.output, dll_lookup_dirs)
