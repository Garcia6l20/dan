import json
import os
from pathlib import Path
import re
from shutil import which
import subprocess
from dan.core.runners import sync_run


def _system_registry_key(key, subkey, query):
    from winreg import winreg  # @UnresolvedImport
    try:
        hkey = winreg.OpenKey(key, subkey)
    except (OSError, WindowsError):  # Raised by OpenKey/Ex if the function fails (py3, py2)
        return None
    else:
        try:
            value, _ = winreg.QueryValueEx(hkey, query)
            return value
        except EnvironmentError:
            return None
        finally:
            winreg.CloseKey(hkey)

def cygpath(p: str|Path, reverse=False) -> str:
    if not reverse:
        if isinstance(p, str):
            p = Path(p)
        absolute = p.is_absolute()
        p = p.as_posix()
        if absolute:
            p = '/' + p[0].lower() + p[2:]
    else:
        if isinstance(p, Path):
            p = p.as_posix()
        if p.startswith('/'):
            p = p[1].upper() + ':' + p[2:]
    return p


def _enum_keys(hkey):
    import winreg  # @UnresolvedImport
    try:
        index = 0
        while True:
            subkey = winreg.EnumKey(hkey, index)
            yield subkey
            index += 1
    except (OSError, WindowsError):  # Raised by OpenKey/Ex if the function fails (py3, py2)
        pass

def _enum_values(hkey):
    import winreg  # @UnresolvedImport
    try:
        index = 0
        while True:
            subkey = winreg.EnumValue(hkey, index)
            yield subkey
            index += 1
    except (OSError, WindowsError):  # Raised by OpenKey/Ex if the function fails (py3, py2)
        pass

def _key_values(hkey) -> dict:
    result = dict()
    for name, value, _tp in _enum_values(hkey):
        result[name] = value
    return result


# b0109e3f-1479-4d53-8b2d-e4efacbc27c9
def find_installation_data(match, flags=0):
    import winreg  # @UnresolvedImport
    base = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
    hkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, base)
    for subkey in _enum_keys(hkey):
        subkey = base + '\\' + subkey
        skey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey)
        values = _key_values(skey)
        if re.match(match, values.get('DisplayName', ''), flags):
            return values


def is_win64():
    import winreg  # @UnresolvedImport
    return _system_registry_key(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Windows\CurrentVersion",
                                "ProgramFilesDir (x86)") is not None


def vswhere(all_=False, prerelease=False, products=None, requires=None, version="", latest=False,
            legacy=False, property_="", nologo=True):

    # 'version' option only works if Visual Studio 2017 is installed:
    # https://github.com/Microsoft/vswhere/issues/91

    products = list() if products is None else products
    requires = list() if requires is None else requires

    if legacy and (products or requires):
        raise RuntimeError("The 'legacy' parameter cannot be specified with either the "
                           "'products' or 'requires' parameter")

    installer_path = None
    program_files = os.getenv("ProgramFiles(x86)") or os.getenv("ProgramFiles")
    if program_files:
        expected_path = os.path.join(program_files, "Microsoft Visual Studio", "Installer",
                                     "vswhere.exe")
        if os.path.isfile(expected_path):
            installer_path = expected_path
    vswhere_path = installer_path or which("vswhere")

    if not vswhere_path:
        raise RuntimeError("Cannot locate vswhere in 'Program Files'/'Program Files (x86)' "
                           "directory nor in PATH")

    arguments = list()
    arguments.append(vswhere_path)

    # Output json format
    arguments.append("-format")
    arguments.append("json")

    if all_:
        arguments.append("-all")

    if prerelease:
        arguments.append("-prerelease")

    if products:
        arguments.append("-products")
        arguments.extend(products)

    if requires:
        arguments.append("-requires")
        arguments.extend(requires)

    if len(version) != 0:
        arguments.append("-version")
        arguments.append(version)

    if latest:
        arguments.append("-latest")

    if legacy:
        arguments.append("-legacy")

    if len(property_) != 0:
        arguments.append("-property")
        arguments.append(property_)

    if nologo:
        arguments.append("-nologo")

    try:
        output, err, rc = sync_run(arguments, no_raise=True)
        if rc != 0:
            raise RuntimeError(err.strip())
        output = output.strip()
        # Ignore the "description" field, that even decoded contains non valid charsets for json
        # (ignored ones)
        output = "\n".join([line for line in output.splitlines()
                            if not line.strip().startswith('"description"')])

    except (ValueError, subprocess.CalledProcessError, UnicodeDecodeError) as e:
        raise RuntimeError("vswhere error: %s" % str(e))

    return json.loads(output)
