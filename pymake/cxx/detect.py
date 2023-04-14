import logging
import os
from pymake.core.pathlib import Path
import subprocess
import sys
import tempfile
import functools

import yaml
from pymake.core.find import find_executable

from pymake.core.osinfo import info as osinfo
from pymake.core.runners import sync_run
from pymake.core.version import Version
from pymake.core.win import vswhere


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


def detect_compiler_id(executable, env=None):
    # use a temporary file, as /dev/null might not be available on all platforms
    tmpdir = tempfile.mkdtemp(prefix='pymake-dci-')
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
        ['-dM', '-E', '-x', 'c'],
        ['--driver-mode=g++', '-dM', '-E', '-x', 'c'],  # clang-cl
        ['-c', '-xdumpmacros'],  # SunCC,
        # cl (Visual Studio, MSVC)
        # "/nologo" Suppress Startup Banner
        # "/E" Preprocess to stdout
        # "/B1" C front-end
        # "/c" Compile Without Linking
        # "/TC" Specify Source File Type
        ['/nologo', '/E', '/B1', cmd, '/c', '/TC'],
        ['/QdM', '/E', '/TC'],  # icc (Intel) on Windows,
        ['-Wp', '-dM', '-E', '-x', 'c'],  # QNX QCC
    ]
    try:
        for detector in detectors:
            output, _, rc = sync_run(
                [executable, *detector, tmpname], no_raise=True, env=env, cwd=tmpdir)
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
    def __init__(self, path: Path, arch: str = None, env: dict[str, str] = None, tools: dict[str, Path] = dict()) -> None:
        self.path = path
        self.compiler_id = detect_compiler_id(path, env=env)
        if self.compiler_id is None:
            raise RuntimeError(f'Cannot detect compiler ID of {self.path}')
        self.name = self.compiler_id.name
        self.arch = arch
        self.env = env
        self.tools = tools

    @ property
    def version(self):
        return self.compiler_id.version

    def __str__(self) -> str:
        return f'{self.compiler_id} {self.arch + " " if self.arch else ""}({self.path})'

    def __eq__(self, other: 'Compiler'):
        return self.path == other.path

    def __hash__(self):
        return hash(self.path)


def validate_pair(ob):
    try:
        if not (len(ob) == 2):
            print("Unexpected result:", ob, file=sys.stderr)
            raise ValueError
    except:
        return False
    return True


def get_environment_from_batch_command(env_cmd, initial=None):
    """
    Take a command (either a single command or list of arguments)
    and return the environment created after running that command.
    Note that if the command must be a batch file or .cmd file, or the
    changes to the environment will not be captured.

    If initial is supplied, it is used as the initial environment passed
    to the child process.
    """
    def consume(iter):
        try:
            while True:
                next(iter)
        except StopIteration:
            pass
    if not isinstance(env_cmd, (list, tuple)):
        env_cmd = [env_cmd]
    # construct the command that will alter the environment
    env_cmd = subprocess.list2cmdline(env_cmd)
    # create a tag so we can tell in the output when the proc is done
    if os.name == 'nt':
        # construct a cmd.exe command to do accomplish this
        cmd = f'cmd.exe /s /c "{env_cmd} && set"'
        enc = 'cp1252'
        shell = False
    else:
        cmd = f"sh -c '. {env_cmd} && env'"
        enc = 'utf-8'
        shell = True
    # launch the process
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            env=initial, shell=shell)
    # parse the output sent to stdout
    out, _ = proc.communicate()
    result = dict()
    for line in out.decode(enc).splitlines():
        line = line.strip()
        pos = line.find('=')
        if pos > 0:
            name = line[:pos].strip()
            value = line[pos + 1:].strip()
            # if os.getenv(name) != value:
            #    result[name] = value
            result[name] = value
    return result


def get_compilers(logger: logging.Logger):
    from pymake.core.find import find_executables, find_executable, find_file
    compilers: set[Compiler] = set()
    if os.name == 'nt':
        infos = vswhere()
        for info in infos:
            logger.info(f'Loading Visual Studio: {info["displayName"]}')
            paths = [info['installationPath']]
            cl = find_executable('cl', paths=paths, default_paths=False)
            link = find_executable(
                'link', paths=[cl.parent], default_paths=False)
            lib = find_executable(
                'lib', paths=[cl.parent], default_paths=False)
            vcvars = find_file(r'vcvarsall.bat', paths=paths)
            archs = [('x86_64', 'x64'), ('x86', 'x86')]
            for arch, vc_arch in archs:
                env = get_environment_from_batch_command([vcvars, vc_arch])
                if env:
                    compilers.add(Compiler(cl, arch=arch, env=env,
                                  tools={'link': link, 'lib': lib}))
                else:
                    logger.warning(
                        f'Cannot load msvc with {arch} architecture')
    else:
        for gcc in find_executables(r'gcc(-\d+)?'):
            gcc = gcc.resolve()
            compilers.add(Compiler(gcc))
        for clang in find_executables(r'clang(-\d+)?'):
            clang = clang.resolve()
            compilers.add(Compiler(clang))
    return compilers


if os.name != 'nt':
    _required_tools = [
        'nm', 'ranlib', 'strip', 'readelf', 'ar', 'ranlib'
    ]
else:
    _required_tools = list()


def create_toolchain(compiler: Compiler, logger=logging.getLogger('toolchain')):
    logger.info(f'scanning {compiler.compiler_id} toolchain')
    data = {
        'type': compiler.name,
        'version': str(compiler.version),
        'cc': str(compiler.path),
    }
    pos = compiler.path.stem.rfind(compiler.name)
    if pos >= 0:
        prefix = None if pos == 0 else compiler.path.stem[:pos]
        base_name = compiler.name
        suffix = compiler.path.stem[pos + len(compiler.name):]
    else:
        prefix = None
        base_name = compiler.path.stem
        suffix = None
    base_path = compiler.path.parent

    if compiler.arch:
        data['arch'] = compiler.arch

    if compiler.env:
        data['env'] = compiler.env

    def get_compiler_tool(tool, toolname=None):
        if not toolname:
            toolname = f'{base_name}-{tool}'
        if prefix:
            toolname = f'{prefix}{toolname}'
        if suffix:
            toolname = f'{toolname}{suffix}'
        tool_path = base_path / toolname
        if tool_path.exists():
            logger.debug(f'found {tool} tool: {tool_path}')
            data[tool] = str(tool_path)
        else:
            logger.debug(f'{tool} tool not found: {tool_path}')
    if compiler.name == 'gcc':
        get_compiler_tool('cxx', 'g++')
        get_compiler_tool('as')
    elif compiler.name == 'clang':
        get_compiler_tool('cxx', 'clang++')
    elif compiler.name == 'msvc':
        data['link'] = str(compiler.tools['link'])
        data['lib'] = str(compiler.tools['lib'])

    for tool in _required_tools:
        get_compiler_tool(tool)

    name = str(compiler.compiler_id)
    if prefix:
        name = f'{prefix}{name}'
    if suffix:
        name = f'{name}{suffix}'
    return name, data


_home_var = 'USERPROFILE' if os.name == 'nt' else 'HOME'


@ functools.cache
def get_pymake_path():
    path = Path(os.getenv('PYMAKE_DATA', os.getenv(_home_var))) / '.pymake'
    path.mkdir(exist_ok=True, parents=False)
    return path


def get_toolchain_path():
    return get_pymake_path() / 'toolchains.yaml'


def load_env_toolchain(script: Path = None, name: str = None):
    logger = logging.getLogger('toolchain')
    env = get_environment_from_batch_command(script)
    arch = env['ARCH'] if 'ARCH' in env else None
    paths = env['PATH'].split(os.pathsep)

    def patch_flags(name, flagsname):
        parts = env[name].split(' ')
        env[name] = parts[0]
        env[flagsname] = ' '.join(
            set([*env[flagsname].split(' '), *parts[1:]]))
    # split CC/CFLAGS
    patch_flags('CC', 'CFLAGS')
    patch_flags('CXX', 'CXXFLAGS')
    patch_flags('LD', 'LDFLAGS')
    if 'CPP' in env:
        del env['CPP']
    if 'CPPFLAGS' in env:
        del env['CPPFLAGS']

    cc_path = find_executable(env['CC'], paths, default_paths=False)
    cc = Compiler(Path(cc_path), arch=arch, env=env)
    tname, toolchain = create_toolchain(cc, logger)
    save_toolchain(name or tname, toolchain)


def save_toolchain(name, toolchain):
    toolchains_path = get_toolchain_path()
    logger = logging.getLogger('toolchain')
    logger.setLevel(logging.INFO)
    if toolchains_path.exists():
        with open(toolchains_path, 'r+') as f:
            logger.info(f'updating toolchains file {toolchains_path}')
            data = yaml.load(f.read(), Loader=yaml.FullLoader)
            toolchains = data['toolchains']
            toolchains[name] = toolchain
            f.seek(0)
            f.truncate()
            f.write(yaml.dump(data))


def create_toolchains():
    import yaml
    from pymake.core.find import find_executable
    toolchains_path = get_toolchain_path()
    logger = logging.getLogger('toolchain')
    logger.setLevel(logging.INFO)
    data = None
    if toolchains_path.exists():
        with open(toolchains_path, 'r') as f:
            logger.info(f'updating toolchains file {toolchains_path}')
            data = yaml.load(f.read(), Loader=yaml.FullLoader)
            if data:
                toolchains = data['toolchains']
                tools = data['tools']
    if not data:
        data = dict()
        toolchains = dict()
        tools = dict()

    compilers = get_compilers(logger)
    for cc in compilers:
        k, v = create_toolchain(cc, logger)
        if not k in toolchains.keys():
            logger.info(f'new toolchain \'{k}\' found')
        elif toolchains[k] != v:
            logger.info(f'updating toolchain \'{k}\'')
        else:
            logger.info(f'toolchain \'{k}\' unchanged')
            continue
        toolchains[k] = v
    for tool in _required_tools:
        tools[tool] = str(find_executable(tool))
    data['tools'] = tools
    data['toolchains'] = toolchains
    if not 'default' in data:
        data['default'] = list(toolchains.keys())[0]
    with open(toolchains_path, 'w') as f:
        f.write(yaml.dump(data))
    return data


def get_toolchains():
    import yaml
    toolchains_path = get_toolchain_path()
    if not toolchains_path.exists():
        return create_toolchains()

    with open(toolchains_path) as f:
        data = yaml.load(f, yaml.FullLoader)
        return data if data else create_toolchains()
