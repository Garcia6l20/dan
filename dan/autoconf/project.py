from dan.core.target import Target, Installer
from dan.core.runners import async_run
from dan.core.find import find_executable, find_files
from dan.core.pm import re_match
from dan.core import asyncio, aiofiles
from dan.core.utils import chunks
from dan.cxx import Toolchain

from pathlib import Path
import os
import re

class Project(Target, internal=True):
    env: dict[str, str] = None
    configure_output: Path|str = None
    configure_options: list[str] = None
    make_options: list[str] = None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.toolchain: Toolchain = self.context.get('cxx_target_toolchain')
        self.output = 'libav.built'
        self.__make = self.cache.get('make_path', None)
        
    @property
    def make(self):
        if self.__make is None:
            if self.toolchain.system.startswith('msys'):
                from dan.core.win import find_installation_data
                data = find_installation_data('MSYS2')
                self.__make = find_executable(r'.+make', data['InstallLocation'], default_paths=False)
                if self.__make is None:
                    raise RuntimeError('cannot find make')
                self.cache['make_path'] = self.__make
            else:
                self.__make = 'make'
        return self.__make

    def __get_make_args(self):
        make_args = []
        if self.make_options is not None:
            make_args.extend(self.make_options)
        return make_args
    
    def __get_env(self):
        env = dict(self.toolchain.env)
        if self.env is not None:
            for k, v in self.env.items():
                env[k] = v
        env['PKG_CONFIG_PATH'] = str(self.makefile.root.pkgs_path)
        env['CC'] = str(self.toolchain.cc)
        env['CXX'] = str(self.toolchain.cxx)
        return env

    async def __build__(self):
        if not self.toolchain.system.is_linux and not self.toolchain.system.startswith('msys'):
            raise RuntimeError(f'{self.name} can only be built on linux or msys2-mingw')

    async def do_compile(self, obj, options, env):
        self.info('generating %s', obj)
        await async_run(f'{self.toolchain.cc} {options}', logger=self, cwd=self.build_path, env=env)
        self.info('%s generated', obj)
        
    async def do_ar(self, lib, ar_arg, objects: list[str], builds, env):
        self.info('generating %s objects', lib)

        async with asyncio.TaskGroup(f'generating {lib} objects') as obj_builds:
            for obj in objects:
                if obj in builds:
                    obj_builds.create_task(builds[obj])

        command = f'{self.toolchain.ar} {ar_arg} {lib} {" ".join(objects)}'
        windows_command_line_limitation = 8191
        if os.name == 'nt' and len(command) >= windows_command_line_limitation:
            # workaround command-line size limitation
            objects_dir = self.build_path / f'{lib}_objects'
            if objects_dir.exists():
                await aiofiles.rmtree(objects_dir)
            objects_dir.mkdir()
            for obj in objects:
                obj_path = Path(self.build_path / obj)
                dest = objects_dir / obj_path.relative_to(objects_dir.parent).as_posix().replace('/', '_')
                if not dest.exists():
                    obj_path.rename(dest)
                
            command = f'{self.toolchain.ar} {ar_arg} {lib} {(objects_dir.relative_to(self.build_path) / "*.o").as_posix()}'
                
        self.info('creating static library %s', lib)
        await async_run(command, logger=self, cwd=self.build_path, env=env)
        self.info('static library %s created', lib)

    async def do_ld(self, output, lib_paths, objects, libs, builds: dict[str, asyncio.Task], env):
        self.info('generating %s dependencies', output)

        async with asyncio.TaskGroup(f'generating {output} objects') as grp:
            for obj in objects:
                if obj in builds:
                    grp.create_task(builds[obj])

        async with asyncio.TaskGroup(f'generating {output} dependencies') as grp:
            seen = set()
            for lib in re.split(r'\s+', libs):
                lib = lib[2:]
                if lib not in seen:
                    seen.add(lib)
                    for l in builds:
                        if re.search(rf'lib{lib}\.(a|so|dll|lib)', l):
                            grp.create_task(builds[l])

        self.info('linking %s', output)
        await async_run(f'{self.toolchain.cc} {lib_paths} -o {output} {" ".join(objects)} {libs}', logger=self, cwd=self.build_path, env=env)
        self.info('%s linked', output)
    
    @staticmethod
    async def patch_makefile(makefile: Path):
        from dan.core.win import cygpath
        bak = makefile.with_suffix('.bak')
        bak.unlink(missing_ok=True)
        makefile.rename(bak)
        async with aiofiles.open(bak) as i, aiofiles.open(makefile, 'w') as o:
            for line in await i.readlines():
                m = re.match(r'(.+?[= ])(/.+)', line)
                if m:
                    line = m[1] + cygpath(m[2], reverse=True) + '\n'
                    await o.write(line)
                else:
                    await o.write(line)


    async def __install__(self, installer: Installer):
        config_options = []
        if self.configure_options is not None:
            config_options.extend(self.configure_options)
        config_options.append(f'--prefix={installer.settings.destination}')

        env = self.__get_env()
        await async_run(['bash', self.source_path / 'configure', *config_options], cwd=self.build_path, logger=self, env=env)

        if not self.toolchain.system.is_linux:
            # patch MakeFiles
            makefile = Path(self.build_path / 'Makefile')
            if makefile.exists():
                await self.patch_makefile(makefile)
            
            for makefile in find_files(r'.+\.mak', self.build_path):
                await self.patch_makefile(makefile)

        builds = dict()
        installs = list()

        async with asyncio.TaskGroup(f'executing make {self.name}') as g:
            async def wrap_executor(stream):
                with stream as lines:
                    async for line in lines:
                        line = line.strip()
                        match re_match(line):
                            case r'.+CC.+? (.+\.o); (.+?) (.+)' as m:
                                obj = m[1]
                                # cc = m[2]
                                options = m[3]
                                builds[obj] = asyncio.create_task(self.do_compile(obj, options, env))

                            case r'.+AR.+? (.+\.a); (.+?) (.+?) (.+\.a) (.+)' as m:
                                lib = m[1]
                                # ar = m[2]
                                ar_arg = m[3]
                                objects = m[5].split(' ')
                                builds[lib] = asyncio.create_task(self.do_ar(lib, ar_arg, objects, builds, env))

                            case r'.+LD.+? (.+); (.+?) (.+?)\s?-o (.+?) (.+?) (-l.+)' as m:
                                lib_paths = m[3]
                                output = m[4]
                                objects = m[5].split(' ')
                                libs = m[6]
                                builds[output] = asyncio.create_task(self.do_ld(output, lib_paths, objects, libs, builds, env))
                                
                            case r'.+INSTALL.+? (.+?); install (.+(?=-m \d+))?(-m \d+) (.+)' as m:
                                # args = m[2]
                                # mode = m[3]
                                items = str(m[4]).split(' ')
                                dest = items.pop()
                                if dest[0] in ('"', "'"):
                                    dest = dest[1:-1] # unquote
                                dest = Path(dest).expanduser()
                                for item in items:
                                    installs.append(installer._install(self.build_path / item, dest))
                            case _:
                                # by default we assume it will be a bash command
                                await async_run(['bash', '-c', line], logger=self, cwd=self.build_path)

            await async_run([self.make, 'install', '-n', *self.__get_make_args()],
                             cwd=self.build_path, logger=self, log=False,
                             env=env, out_capture=wrap_executor)
        
        async with asyncio.TaskGroup(f'generating {self.name} targets') as g:
            for name, coro in builds.items():
                g.create_task(coro)
            
        for chunk in chunks(installs, 100):
            await asyncio.gather(*chunk)

        await super().__install__(installer)
        self.output.touch()
