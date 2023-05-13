from dan import self
from dan.jinja import generator
from dan.cxx import (
    Library,
    Executable,
    target_toolchain as tc)
from dan.smc import GitSources

version = '2.1'
description = 'Helpers to setup and teardown io_uring instances'

class LibUringSources(GitSources):
    name = 'liburing'
    url = 'https://github.com/axboe/liburing.git'
    refspec = f'liburing-{version}'

def has_kernel_rwf_t():
    return tc.can_compile('''
        #include <linux/fs.h>
        int main(int argc, char **argv)
        {
            __kernel_rwf_t x;
            x = 0;
            return x;
        }
        ''')


def has_kernel_timespec():
    return tc.can_compile('''
        #include <linux/time.h>
        #include <linux/time_types.h>
        int main(int argc, char **argv)
        {
            struct __kernel_timespec ts;
            ts.tv_sec = 0;
            ts.tv_nsec = 1;
            return 0;
        }
        ''')


def has_open_how():
    return tc.can_compile('''
        #include <sys/types.h>
        #include <sys/stat.h>
        #include <fcntl.h>
        #include <string.h>
        int main(int argc, char **argv)
        {
            struct open_how how;
            how.flags = 0;
            how.mode = 0;
            how.resolve = 0;
            return 0;
        }
        ''')


@generator('liburing/host-config.h', 'host-config.h.jinja')
def host_config():
    return {
        'has_kernel_rwf_t': has_kernel_rwf_t(),
        'has_kernel_timespec': has_kernel_timespec(),
        'has_open_how': has_open_how(),
        'has_statx': tc.can_compile('''
            #include <sys/types.h>
            #include <sys/stat.h>
            #include <unistd.h>
            #include <fcntl.h>
            #include <string.h>
            #include <linux/stat.h>
            int main(int argc, char **argv)
            {
                struct statx x;
                return memset(&x, 0, sizeof(x)) != NULL;
            }'''),
        'has_cxx': True,  # maybe not...
        'has_ucontext': tc.can_compile('''#include <ucontext.h>
            int main(int argc, char **argv)
            {
                ucontext_t ctx;
                getcontext(&ctx);
                makecontext(&ctx, 0, 0);
                return 0;
            }
            '''),
        'has_stringop_overflow': tc.has_cxx_compile_options('-Wstringop-overflow'),
        'has_array_bounds': tc.has_cxx_compile_options('-Warray-bounds'),
    }


@generator('liburing/compat.h', 'compat.h.jinja')
def compat():
    return {
        'has_kernel_rwf_t': has_kernel_rwf_t(),
        'has_kernel_timespec': has_kernel_timespec(),
        'has_open_how': has_open_how(),
    }

class LibUring(Library):
    name = 'uring'
    preload_dependencies = LibUringSources, compat,
    private_compile_definitions = '_GNU_SOURCE',

    async def __initialize__(self):
        uring_root = self.get_dependency(LibUringSources).output
        self.sources = (uring_root / 'src').rglob('*.c')
        self.includes = uring_root / 'include', self.build_path        
        return await super().__initialize__()

# test_path = git.output / 'test'
# test_helpers = Library('uring-test-helpers',
#                        sources=[test_path / 'helpers.c'],
#                        includes=[inc, self.build_path],
#                        dependencies=[lib, host_config],
#                        all=False)

# for test in test_path.glob('*.c'):
#     if test.stem == 'helpers':
#         continue
#     exe = Executable(test.stem,
#                      sources=[test],
#                      dependencies=[lib, test_helpers, host_config],
#                      all=False)
#     exe.compile_definitions.add('_GNU_SOURCE')
#     self.add_test(exe)


# self.export(lib)
# self.install(lib)
