import logging
import os
from pathlib import Path
import tempfile

from pymake.core.osinfo import info as osinfo
from pymake.core.utils import SyncRunner
from pymake.core.version import Version


class CompilerId:
    def __init__(self, name: str, version: Version) -> None:
        self.name = name
        self.version = version

    def __str__(self) -> str:
        return f'{self.name}-{self.version}'


GCC = "gcc"
LLVM_GCC = "llvm-gcc"  # GCC frontend with LLVM backend
CLANG = "clang"
APPLE_CLANG = "apple-clang"
SUNCC = "suncc"
VISUAL_STUDIO = "Visual Studio"
INTEL = "intel"
QCC = "qcc"
MCST_LCC = "mcst-lcc"
MSVC = "msvc"

MSVC_TO_VS_VERSION = {800: (1, 0),
                      900: (2, 0),
                      1000: (4, 0),
                      1010: (4, 1),
                      1020: (4, 2),
                      1100: (5, 0),
                      1200: (6, 0),
                      1300: (7, 0),
                      1310: (7, 1),
                      1400: (8, 0),
                      1500: (9, 0),
                      1600: (10, 0),
                      1700: (11, 0),
                      1800: (12, 0),
                      1900: (14, 0),
                      1910: (15, 0),
                      1911: (15, 3),
                      1912: (15, 5),
                      1913: (15, 6),
                      1914: (15, 7),
                      1915: (15, 8),
                      1916: (15, 9),
                      1920: (16, 0),
                      1921: (16, 1),
                      1922: (16, 2),
                      1923: (16, 3),
                      1924: (16, 4),
                      1925: (16, 5),
                      1926: (16, 6),
                      1927: (16, 7),
                      1928: (16, 8),
                      1929: (16, 10),
                      1930: (17, 0)}


def _parse_compiler_version(defines):
    try:
        if '__LCC__' in defines and '__e2k__' in defines:
            compiler = MCST_LCC
            version = int(defines['__LCC__'])
            major = int(version / 100)
            minor = int(version % 100)
            patch = int(defines['__LCC_MINOR__'])
        elif '__INTEL_COMPILER' in defines:
            compiler = INTEL
            version = int(defines['__INTEL_COMPILER'])
            major = int(version / 100)
            minor = int(version % 100)
            patch = int(defines['__INTEL_COMPILER_UPDATE'])
        elif '__clang__' in defines:
            compiler = APPLE_CLANG if '__apple_build_version__' in defines else CLANG
            major = int(defines['__clang_major__'])
            minor = int(defines['__clang_minor__'])
            patch = int(defines['__clang_patchlevel__'])
        elif '__SUNPRO_C' in defines or '__SUNPRO_CC' in defines:
            # In particular, the value of __SUNPRO_CC, which is a three-digit hex number.
            # The first digit is the major release. The second digit is the minor release.
            # The third digit is the micro release. For example, C++ 5.9 is 0x590.
            compiler = SUNCC
            define = '__SUNPRO_C' if '__SUNPRO_C' in defines else '__SUNPRO_CC'
            version = int(defines[define], 16)
            major = (version >> 8) & 0xF
            minor = (version >> 4) & 0xF
            patch = version & 0xF
        # MSVC goes after Clang and Intel, as they may define _MSC_VER
        elif '_MSC_VER' in defines:
            version = int(defines['_MSC_VER'])
            full_version = 0
            if '_MSC_FULL_VER' in defines:
                full_version = int(defines['_MSC_FULL_VER'])
            # Visual Studio 2022 onwards, detect as a new compiler "msvc"
            if version >= 1930:
                compiler = MSVC
                major = int(version / 100)
                minor = int(version % 100)
                patch = int(full_version % 100000)
            else:
                compiler = VISUAL_STUDIO
                # map _MSC_VER into conan-friendly Visual Studio version
                # currently, conan uses major only, but here we store minor for the future as well
                # https://docs.microsoft.com/en-us/cpp/preprocessor/predefined-macros?view=vs-2019
                major, minor = MSVC_TO_VS_VERSION.get(version)
                # special cases 19.8 and 19.9, 19.10 and 19.11
                if (major, minor) == (16, 8) and full_version >= 192829500:
                    major, minor = 16, 9
                if (major, minor) == (16, 10) and full_version >= 192930100:
                    major, minor = 16, 11
                patch = 0
        # GCC must be the last try, as other compilers may define __GNUC__ for compatibility
        elif '__GNUC__' in defines:
            if '__llvm__' in defines:
                compiler = LLVM_GCC
            elif '__QNX__' in defines:
                compiler = QCC
            else:
                compiler = GCC
            major = int(defines['__GNUC__'])
            minor = int(defines['__GNUC_MINOR__'])
            patch = int(defines['__GNUC_PATCHLEVEL__'])
        else:
            return None
        return CompilerId(compiler, Version(major, minor, patch))
    except KeyError:
        return None
    except ValueError:
        return None
    except TypeError:
        return None


def detect_compiler_id(executable):
    # use a temporary file, as /dev/null might not be available on all platforms
    runner = SyncRunner()
    tmpdir = tempfile.mkdtemp()
    tmpname = os.path.join(tmpdir, "temp.c")
    with open(tmpname, "wb") as f:
        f.write(b"\n")

    cmd = os.path.join(tmpdir, "file.cmd")
    with open(cmd, "wb") as f:
        f.write(b"echo off\nset MSC_CMD_FLAGS\n")

    detectors = [
        # "-dM" generate list of #define directives
        # "-E" run only preprocessor
        # "-x c" compiler as C code
        # the output is of lines in form of "#define name value"
        "-dM -E -x c",
        "--driver-mode=g++ -dM -E -x c",  # clang-cl
        "-c -xdumpmacros",  # SunCC,
        # cl (Visual Studio, MSVC)
        # "/nologo" Suppress Startup Banner
        # "/E" Preprocess to stdout
        # "/B1" C front-end
        # "/c" Compile Without Linking
        # "/TC" Specify Source File Type
        '/nologo /E /B1 "%s" /c /TC' % cmd,
        "/QdM /E /TC"  # icc (Intel) on Windows,
        "-Wp,-dM -E -x c"  # QNX QCC
    ]
    try:
        for detector in detectors:
            command = '%s %s "%s"' % (executable, detector, tmpname)
            output, _, rc = runner.run(command, no_raise=True)
            if 0 == rc:
                defines = dict()
                for line in output.splitlines():
                    tokens = line.split(' ', 3)
                    if len(tokens) == 3 and tokens[0] == '#define':
                        defines[tokens[1]] = tokens[2]
                    # MSVC dumps macro definitions in single line:
                    # "MSC_CMD_FLAGS=-D_MSC_VER=1921 -Ze"
                    elif line.startswith("MSC_CMD_FLAGS="):
                        line = line[len("MSC_CMD_FLAGS="):].rstrip()
                        defines = dict()
                        tokens = line.split()
                        for token in tokens:
                            if token.startswith("-D") or token.startswith("/D"):
                                token = token[2:]
                                if '=' in token:
                                    name, value = token.split('=', 2)
                                else:
                                    name, value = token, '1'
                                defines[name] = value
                        break
                compiler = _parse_compiler_version(defines)
                if compiler is None:
                    continue
                return compiler
        return None
    finally:
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


class Compiler:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.compiler_id = detect_compiler_id(path)

    @property
    def name(self):
        return self.compiler_id.name

    @property
    def version(self):
        return self.compiler_id.version

    def __str__(self) -> str:
        return f'{self.compiler_id} ({self.path})'

    def __eq__(self, other: 'Compiler'):
        return self.path == other.path

    def __hash__(self):
        return hash(self.path)


def get_compilers():
    from pymake.core.find import find_executables
    compilers: set[Compiler] = set()
    for gcc in find_executables(r'gcc(-\d+)?'):
        gcc = gcc.resolve()
        compilers.add(Compiler(gcc))
    for clang in find_executables(r'clang(-\d+)?'):
        clang = clang.resolve()
        compilers.add(Compiler(clang))
    return compilers


def create_toolchain(compiler: Compiler, logger=logging.getLogger('toolchain')):
    logger.info(f'creating {compiler.compiler_id} toolchain')
    data = {
        'type': compiler.name,
        'version': str(compiler.version),
        'cc': str(compiler.path),
    }
    pos = compiler.path.stem.rfind('-')
    if pos > 0:
        base_name = compiler.path.stem[:pos]
        suffix = compiler.path.stem[pos + 1:]
    else:
        base_name = compiler.path.stem
        suffix = None
    base_path = compiler.path.parent

    def get_compiler_tool(tool, toolname=None):
        if not toolname:
            toolname = f'{base_name}-{tool}'
        if suffix:
            toolname = f'{toolname}-{suffix}'
        tool_path = base_path / toolname
        if tool_path.exists():
            logger.debug(f'found {tool} tool: {tool_path}')
            data[tool] = str(tool_path)
        else:
            logger.debug(f'{tool} tool not found: {tool_path}')
    if compiler.name == 'gcc':
        get_compiler_tool('cxx', 'g++')
    elif compiler.name == 'clang':
        get_compiler_tool('cxx', 'clang++')
    get_compiler_tool('ar')
    get_compiler_tool('nm')
    get_compiler_tool('strip')
    get_compiler_tool('ranlib')
    return str(compiler.compiler_id), data


def create_toolchains():
    import yaml
    from .detect import get_compilers
    from pymake.core.find import find_executable
    from pymake.core.include import root_makefile
    toolchains_path = root_makefile.source_path / 'toolchains.yaml'
    compilers = get_compilers()
    logger = logging.getLogger('toolchain')
    toolchains = dict()
    tools = dict()
    for cc in compilers:
        k, v = create_toolchain(cc, logger)
        toolchains[k] = v
    required_tools = [
        'nm', 'ranlib', 'strip'
    ]
    for tool in required_tools:
        tools[tool] = str(find_executable(tool))
    data = {'tools': tools, 'toolchains': toolchains, 'default': list(toolchains.keys())[0]}
    with open('toolchains.yaml', 'w') as f:
        f.write(yaml.dump(data))
    return data

def get_toolchains():
    import yaml
    from pymake.core.include import root_makefile
    toolchains_path = root_makefile.source_path / 'toolchains.yaml'
    if not toolchains_path.exists():
        return create_toolchains()
    
    with open(toolchains_path) as f:
        return yaml.load(f, yaml.FullLoader)
