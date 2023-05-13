import logging
import os
from dan.core.pathlib import Path
import subprocess
import sys
import tempfile
import functools

import yaml
from dan.core.find import find_executable

from dan.core.osinfo import info as osinfo
from dan.core.runners import sync_run
from dan.core.version import Version
from dan.core.win import vswhere


class CompilerId:
    def __init__(self, name: str, version: Version, arch: str, system: str) -> None:
        self.name = name
        self.version = version
        self.arch = arch
        self.system = system

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

_arm_defines = {
    'arm2': ('__ARM_ARCH_2__'),
    'arm3': ('__ARM_ARCH_3__', '__ARM_ARCH_3M__'),
    'arm4': ('__ARM_ARCH_4T__', '__TARGET_ARM_4T'),
    'arm5': ('__ARM_ARCH_5_', '__ARM_ARCH_5E_'),
    'arm6': ('__ARM_ARCH_6T2_', '__ARM_ARCH_6T2_', '__ARM_ARCH_6__', '__ARM_ARCH_6J__', '__ARM_ARCH_6K__', '__ARM_ARCH_6Z__', '__ARM_ARCH_6ZK__'),
    'arm7': ('__ARM_ARCH_7__', '__ARM_ARCH_7A__', '__ARM_ARCH_7R__', '__ARM_ARCH_7M__', '__ARM_ARCH_7S__'),
    'arm7a': ('__ARM_ARCH_7A__', '__ARM_ARCH_7R__', '__ARM_ARCH_7M__', '__ARM_ARCH_7S__'),
    'arm7r': ('__ARM_ARCH_7R__', '__ARM_ARCH_7M__', '__ARM_ARCH_7S__'),
    'arm7m': ('__ARM_ARCH_7M__'),
    'arm7s': ('__ARM_ARCH_7S__'),
}

def dict_contains(defines, *defs):
    for d in defs:
        if d in defines:
            return True
    return False

def get_target_system(defines: dict[str, str]) -> str:
    system = None
    if dict_contains(defines, '_WIN32', '_WIN64'):
        system = 'windows'
    elif dict_contains(defines, '__ANDROID__'):
        system = 'android'
    elif dict_contains(defines, '__linux__'):
        system = 'linux'
    elif dict_contains(defines, '__sun'):
        system = 'sun'
    elif dict_contains(defines, '__hpux'):
        system = 'hpux'
    elif dict_contains(defines, '__DragonFly__'):
        system = 'dragonfly'
    elif dict_contains(defines, '__FreeBSD__'):
        system = 'freebsd'
    elif dict_contains(defines, '__NetBSD__'):
        system = 'netbsd'
    elif dict_contains(defines, '__OpenBSD__'):
        system = 'openbsd'
    elif dict_contains(defines, 'BSD'):
        system = 'bsd'
    elif dict_contains(defines, '__unix__'):
        system = 'unix'
    elif dict_contains(defines, '__MACH__', '__APPLE__'):
        system = 'macos'
    return system

def get_target_arch(defines: dict[str, str]) -> str:
    arch = None
    if dict_contains(defines, '__x86_64__', '_M_X64'):
        arch = 'x64'
    elif dict_contains(defines, 'i386', '__i386__', '__i386', '_M_IX86'):
        arch = 'x86'
    elif dict_contains(defines, '__aarch64__', '_M_ARM64'):
        arch = 'arm64'
    elif '_M_ARM' in defines:
        arch = 'arm'
    else:
        for defs in _arm_defines:
            if dict_contains(defines, *defs):
                arch = 'arm'
                break
    return arch

def _parse_compiler_version(defines: dict[str, str]):
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
        
        system = get_target_system(defines)
        arch = get_target_arch(defines)

        return CompilerId(compiler, Version(major, minor, patch), arch=arch, system=system)
    except KeyError:
        return None
    except ValueError:
        return None
    except TypeError:
        return None

__data_path = Path(__file__).parent / 'data'
__empty_source = __data_path / 'empty.c'
__detect_cmd = __data_path / 'detect.cmd'

detectors = {
    # "-dM" generate list of #define directives
    # "-E" run only preprocessor
    # "-x c" compiler as C code
    # the output is of lines in form of "#define name value"
    'gcc': ['-dM', '-E', '-x', 'c'],
    'clang': ['-dM', '-E', '-x', 'c'],
    'clang-cl': ['--driver-mode=g++', '-dM', '-E', '-x', 'c'],
    'sun-cc': ['-c', '-xdumpmacros'], 
    # cl (Visual Studio, MSVC)
    # "/nologo" Suppress Startup Banner
    # "/E" Preprocess to stdout
    # "/B1" C front-end
    # "/c" Compile Without Linking
    # "/TC" Specify Source File Type
    'msvc': ['/nologo', '/E', '/B1', str(__detect_cmd), '/c', '/TC'],
    'icc': ['/QdM', '/E', '/TC'],  # icc (Intel) on Windows,
    'qcc': ['-Wp', '-dM', '-E', '-x', 'c'],  # QNX QCC
}

def parse_compiler_defines(output: str):
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
    return defines

def get_compiler_defines(executable: str, compiler_type: str, options: list[str], env=None):
    with tempfile.TemporaryDirectory(prefix='dan-dci-') as tmpdir:
        output, _, rc = sync_run(
                [executable, *detectors[compiler_type], *options, str(__empty_source)], env=env, cwd=tmpdir)
        return parse_compiler_defines(output)


def detect_compiler_id(executable, env=None):
    # use a temporary file, as /dev/null might not be available on all platforms
    with tempfile.TemporaryDirectory(prefix='dan-dci-') as tmpdir:
        for name, detector in detectors.items():
            output, _, rc = sync_run(
                [executable, *detector, str(__empty_source)], no_raise=True, env=env, cwd=tmpdir)
            if 0 == rc:
                defines = parse_compiler_defines(output)
                compiler = _parse_compiler_version(defines)
                if compiler is None:
                    continue
                return compiler
        return None


class Compiler:
    def __init__(self, path: Path, env: dict[str, str] = None, tools: dict[str, Path] = dict()) -> None:
        self.path = path
        self.compiler_id = detect_compiler_id(path, env=env)
        if self.compiler_id is None:
            raise RuntimeError(f'Cannot detect compiler ID of {self.path}')
        self.name = self.compiler_id.name
        self.env = env
        self.tools = tools

    @property
    def arch(self):
        return self.compiler_id.arch

    @property
    def system(self):
        return self.compiler_id.system
    
    @property
    def version(self):
        return self.compiler_id.version
    
    @property
    def defines(self):
        return self.compiler_id.defines

    def __str__(self) -> str:
        return f'{self.compiler_id} {self.arch + " " if self.arch else ""}({self.path})'

    def __eq__(self, other: 'Compiler'):
        return self.path == other.path and self.arch == other.arch and self.system == other.system

    def __hash__(self):
        return hash(self.path) ^ hash(self.arch) ^ hash(self.system)


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
    from dan.core.find import find_executables, find_executable, find_file
    compilers: set[Compiler] = set()
    if os.name == 'nt':
        infos = vswhere()
        for info in infos:
            logger.info(f'Loading Visual Studio: {info["displayName"]}')
            paths = [info['installationPath']]
            vcvars = find_file(r'vcvarsall.bat$', paths=paths)
            archs = [('x86_64', 'x64'), ('x86', 'x86')]
            for arch, vc_arch in archs:
                env = get_environment_from_batch_command([vcvars, vc_arch])
                paths = env['PATH'].split(';')
                cl = find_executable('cl', paths=paths, default_paths=False)
                link = find_executable(
                    'link', paths=[cl.parent], default_paths=False)
                lib = find_executable(
                    'lib', paths=[cl.parent], default_paths=False)
                if env:
                    cc = Compiler(cl, env=env,
                                  tools={'link': link, 'lib': lib})
                    assert cc.arch == vc_arch
                    compilers.add(cc)
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

    data['arch'] = compiler.arch
    data['system'] = compiler.system

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


@functools.cache
def get_dan_path():
    path = Path(os.getenv('DAN_DATA', os.getenv(_home_var))) / '.dan'
    path.mkdir(exist_ok=True, parents=False)
    return path


def get_toolchain_path():
    return get_dan_path() / 'toolchains.yaml'


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
    from dan.core.find import find_executable
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
            if toolchains[k]['type'] == v['type'] and toolchains[k]['arch'] != v['arch']:                
                # add arch suffix
                old_arch = toolchains[k]['arch']
                logger.info(f'renaming \'{k}\' -> \'{k}-{old_arch}\'')
                toolchains[f'{k}-{old_arch}'] = toolchains.pop(k)
                logger.info(f'new toolchain \'{k}-{v["arch"]}\' found')
                toolchains[f'{k}-{v["arch"]}'] = v
            else:
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
