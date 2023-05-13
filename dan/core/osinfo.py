
import os
import platform
from shutil import which
import subprocess
import tempfile

from dan.core.version import Version
import logging

_logger = logging.getLogger('os-info')


class CalledProcessErrorWithStderr(subprocess.CalledProcessError):
    def __str__(self):
        ret = super(CalledProcessErrorWithStderr, self).__str__()
        if self.output:
            ret += "\n" + self.output.decode()
        return ret


def load(path):
    """ Loads a file content """
    with open(path, 'r') as handle:
        return handle.read().decode()


def check_output_runner(cmd, stderr=None):
    # Used to run several utilities, like Pacman detect, AIX version, uname, SCM
    d = tempfile.mkdtemp()
    tmp_file = os.path.join(d, "output")
    try:
        # We don't want stderr to print warnings that will mess the pristine outputs
        stderr = stderr or subprocess.PIPE
        cmd = cmd if isinstance(cmd, str) else subprocess.list2cmdline(cmd)
        command = '{} > "{}"'.format(cmd, tmp_file)
        _logger.info("Calling command: {}".format(command))
        process = subprocess.Popen(command, shell=True, stderr=stderr)
        stdout, stderr = process.communicate()
        _logger.info("Return code: {}".format(int(process.returncode)))

        if process.returncode:
            # Only in case of error, we print also the stderr to know what happened
            raise CalledProcessErrorWithStderr(
                process.returncode, cmd, output=stderr)

        output = load(tmp_file)
        try:
            _logger.info("Output: in file:{}\nstdout: {}\nstderr:{}".format(
                output, stdout, stderr))
        except Exception as exc:
            _logger.error("Error logging command output: {}".format(exc))
        return output
    finally:
        try:
            os.rmdir(d)
        except OSError:
            pass


class OSInfo(object):
    """ Usage:
        (os_info.is_linux) # True/False
        (os_info.is_windows) # True/False
        (os_info.is_macos) # True/False
        (os_info.is_freebsd) # True/False
        (os_info.is_solaris) # True/False

        (os_info.linux_distro)  # debian, ubuntu, fedora, centos...

        (os_info.os_version) # 5.1
        (os_info.os_version_name) # Windows 7, El Capitan

        if os_info.os_version > "10.1":
            pass
        if os_info.os_version == "10.1.0":
            pass
    """

    def __init__(self):
        system = platform.system().lower()
        self.name = system
        self.version = None
        self.version_name = None
        self.is_linux = system == "linux"
        self.linux_distro = None
        self.is_msys = system.startswith(
            "ming") or system.startswith("msys_nt")
        self.is_cygwin = system.startswith("cygwin_nt")
        self.is_windows = system == "windows" or self.is_msys or self.is_cygwin
        self.is_macos = system == "darwin"
        self.is_freebsd = system == "freebsd"
        self.is_solaris = system == "sunos"
        self.is_aix = system == "aix"
        self.is_posix = os.pathsep == ':'

        if self.is_linux:
            self._get_linux_distro_info()
        elif self.is_windows:
            self.version = self._get_win_os_version()
            self.version_name = self._get_win_version_name(self.version)
        elif self.is_macos:
            self.name = "macos"
            self.version = Version(platform.mac_ver()[0])
            self.version_name = self._get_osx_version_name(self.version)
        elif self.is_freebsd:
            self.version = self._get_freebsd_version()
            self.version_name = "freebsd %s" % self.version
        elif self.is_solaris:
            self.version = Version(platform.release())
            self.version_name = self._get_solaris_version_name(
                self.version)
        elif self.is_aix:
            self.version = self._get_aix_version()
            self.version_name = "aix %s" % self.version.minor(fill=False)

    def _get_linux_distro_info(self):
        import distro
        self.linux_distro = distro.id()
        self.version = Version(distro.version())
        version_name = distro.codename()
        self.version_name = version_name if version_name != "n/a" else ""
        if not self.version_name and self.linux_distro == "debian":
            self.version_name = self._get_debian_version_name(self.version)

    @property
    def arch(self):
        match platform.machine():
            case 'i386':
                return 'x86'
            case 'AMD64' | 'x86_64':
                return 'x64'
            case _ as arch:
                return arch

    @property
    def with_apt(self):
        if not self.is_linux:
            return False

        # https://github.com/conan-io/conan/issues/8737 zypper-aptitude can fake it
        if "opensuse" in self.linux_distro or "sles" in self.linux_distro:
            return False

        apt_location = which('apt-get')
        if apt_location:
            # Check if we actually have the official apt package.
            try:
                output = check_output_runner([apt_location, 'moo'])
            except CalledProcessErrorWithStderr:
                return False
            else:
                # Yes, we have mooed today. :-) MOOOOOOOO.
                return True
        else:
            return False

    @property
    def with_yum(self):
        return self.is_linux and self.linux_distro in ("pidora", "fedora", "scientific", "centos",
                                                       "redhat", "rhel", "xenserver", "amazon",
                                                       "oracle", "amzn", "almalinux", "rocky")

    @property
    def with_dnf(self):
        return self.is_linux and self.linux_distro == "fedora" and which('dnf')

    @property
    def with_pacman(self):
        if self.is_linux:
            return self.linux_distro in ["arch", "manjaro"]
        elif self.is_windows and which('uname.exe'):
            uname = check_output_runner(['uname.exe', '-s'])
            return uname.startswith('MSYS_NT') and which('pacman.exe')
        return False

    @property
    def with_zypper(self):
        if not self.is_linux:
            return False
        if "opensuse" in self.linux_distro or "sles" in self.linux_distro:
            return True
        return False

    @staticmethod
    def _get_win_os_version():
        """
        Get's the OS major and minor versions.  Returns a tuple of
        (OS_MAJOR, OS_MINOR).
        """
        import ctypes

        class _OSVERSIONINFOEXW(ctypes.Structure):
            _fields_ = [('dwOSVersionInfoSize', ctypes.c_ulong),
                        ('dwMajorVersion', ctypes.c_ulong),
                        ('dwMinorVersion', ctypes.c_ulong),
                        ('dwBuildNumber', ctypes.c_ulong),
                        ('dwPlatformId', ctypes.c_ulong),
                        ('szCSDVersion', ctypes.c_wchar * 128),
                        ('wServicePackMajor', ctypes.c_ushort),
                        ('wServicePackMinor', ctypes.c_ushort),
                        ('wSuiteMask', ctypes.c_ushort),
                        ('wProductType', ctypes.c_byte),
                        ('wReserved', ctypes.c_byte)]

        os_version = _OSVERSIONINFOEXW()
        os_version.dwOSVersionInfoSize = ctypes.sizeof(os_version)
        if not hasattr(ctypes, "windll"):
            return None
        retcode = ctypes.windll.Ntdll.RtlGetVersion(ctypes.byref(os_version))
        if retcode != 0:
            return None

        return Version("%d.%d" % (os_version.dwMajorVersion, os_version.dwMinorVersion))

    @staticmethod
    def _get_debian_version_name(version):
        if not version:
            return None
        elif version.major == 8:
            return "jessie"
        elif version.major == 7:
            return "wheezy"
        elif version.major == 6:
            return "squeeze"
        elif version.major == 5:
            return "lenny"
        elif version.major == 4:
            return "etch"
        elif version >= Version(3, 1):
            return "sarge"
        elif version >= Version(3, 0):
            return "woody"

    @staticmethod
    def _get_win_version_name(version):
        if not version:
            return None
        elif version.major == 5:
            return "Windows XP"
        elif version >= Version(6, 0):
            return "Windows Vista"
        elif version >= Version(6, 1):
            return "Windows 7"
        elif version >= Version(6, 2):
            return "Windows 8"
        elif version >= Version(6, 3):
            return "Windows 8.1"
        elif version >= Version(10):
            return "Windows 10"

    @staticmethod
    def _get_osx_version_name(version):
        if not version:
            return None
        elif version >= Version(10, 13):
            return "High Sierra"
        elif version >= Version(10, 12):
            return "Sierra"
        elif version >= Version(10, 11):
            return "El Capitan"
        elif version >= Version(10, 10):
            return "Yosemite"
        elif version >= Version(10, 9):
            return "Mavericks"
        elif version >= Version(10, 8):
            return "Mountain Lion"
        elif version >= Version(10, 7):
            return "Lion"
        elif version >= Version(10, 6):
            return "Snow Leopard"
        elif version >= Version(10, 5):
            return "Leopard"
        elif version >= Version(10, 4):
            return "Tiger"
        elif version >= Version(10, 3):
            return "Panther"
        elif version >= Version(10, 2):
            return "Jaguar"
        elif version >= Version(10, 1):
            return "Puma"
        elif version >= Version(10, 0):
            return "Cheetha"

    @staticmethod
    def _get_aix_architecture():
        processor = platform.processor()
        if "powerpc" in processor:
            kernel_bitness = OSInfo()._get_aix_conf("KERNEL_BITMODE")
            if kernel_bitness:
                return "ppc64" if kernel_bitness == "64" else "ppc32"
        elif "rs6000" in processor:
            return "ppc32"

    @staticmethod
    def _get_solaris_architecture():
        # under intel solaris, platform.machine()=='i86pc' so we need to handle
        # it early to suport 64-bit
        processor = platform.processor()
        kernel_bitness, elf = platform.architecture()
        if "sparc" in processor:
            return "sparcv9" if kernel_bitness == "64bit" else "sparc"
        elif "i386" in processor:
            return "x86_64" if kernel_bitness == "64bit" else "x86"

    @staticmethod
    def _get_e2k_architecture():
        return {
            "E1C+": "e2k-v4",  # Elbrus 1C+ and Elbrus 1CK
            "E2C+": "e2k-v2",  # Elbrus 2CM
            "E2C+DSP": "e2k-v2",  # Elbrus 2C+
            "E2C3": "e2k-v6",  # Elbrus 2C3
            "E2S": "e2k-v3",  # Elbrus 2S (aka Elbrus 4C)
            "E8C": "e2k-v4",  # Elbrus 8C and Elbrus 8C1
            "E8C2": "e2k-v5",  # Elbrus 8C2 (aka Elbrus 8CB)
            "E12C": "e2k-v6",  # Elbrus 12C
            "E16C": "e2k-v6",  # Elbrus 16C
            "E32C": "e2k-v7",  # Elbrus 32C
        }.get(platform.processor())

    @staticmethod
    def _get_freebsd_version():
        return platform.release().split("-")[0]

    @staticmethod
    def _get_solaris_version_name(version):
        if not version:
            return None
        elif version >= Version(5, 10):
            return "Solaris 10"
        elif version >= Version(5, 11):
            return "Solaris 11"

    @staticmethod
    def _get_aix_version():
        try:
            return Version(check_output_runner("oslevel").strip())
        except Exception:
            return Version(platform.version(), platform.release())

    @staticmethod
    def uname(options=None):
        options = " %s" % options if options else ""
        if not OSInfo().is_windows:
            raise RuntimeError("Command only for Windows operating system")
        custom_bash_path = OSInfo.bash_path()
        if not custom_bash_path:
            raise RuntimeError("bash is not in the path")

        command = '"%s" -c "uname%s"' % (custom_bash_path, options)
        try:
            # the uname executable is many times located in the same folder as bash.exe
            with environment_append({"PATH": [os.path.dirname(custom_bash_path)]}):
                ret = check_output_runner(command).strip().lower()
                return ret
        except Exception:
            return None

    @staticmethod
    def _get_aix_conf(options=None):
        options = " %s" % options if options else ""
        if not OSInfo().is_aix:
            raise RuntimeError("Command only for AIX operating system")

        try:
            ret = check_output_runner("getconf%s" % options).strip()
            return ret
        except Exception:
            return None

    @staticmethod
    def _detect_windows_subsystem():
        from conans.client.tools.win import CYGWIN, MSYS2, MSYS, WSL
        if OSInfo().is_linux:
            try:
                # https://github.com/Microsoft/WSL/issues/423#issuecomment-221627364
                with open("/proc/sys/kernel/osrelease") as f:
                    return WSL if f.read().endswith("Microsoft") else None
            except IOError:
                return None
        try:
            output = OSInfo.uname()
        except Exception:
            return None
        if not output:
            return None
        if "cygwin" in output:
            return CYGWIN
        elif "msys" in output or "mingw" in output:
            version = OSInfo.uname("-r").split('.')
            if version and version[0].isdigit():
                major = int(version[0])
                if major == 1:
                    return MSYS
                elif major >= 2:
                    return MSYS2
            return None
        elif "linux" in output:
            return WSL
        else:
            return None
    def __str__(self) -> str:
        return f'{self.linux_distro or self.name} - {self.version_name} ({self.version})'


info = OSInfo()
