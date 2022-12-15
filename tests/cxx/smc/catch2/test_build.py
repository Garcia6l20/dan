import os
from pymake.core.asyncio import OnceLock
from pymake.core.pathlib import Path
import pytest

from pymake.core import aiofiles
from pymake.core.cache import Cache
from pymake.make import Make
from pymake.cxx.detect import get_toolchains
from pymake.cxx.targets import Target

async def prepare_folders():
    source = Path(__file__).parent
    build = source / 'build-pytest'
    if build.exists():
        await aiofiles.rmtree(build)
    os.chdir(source)
    return build, source

def default_toolchain():
    return list(get_toolchains().keys())[0]

async def prepare_make(toolchain = default_toolchain()) -> Make:

    build_path, source_path = await prepare_folders()
    config = Cache(build_path / Make._config_name)
    config.source_path = str(source_path)
    config.build_path = str(build_path)
    config.toolchain = toolchain
    config.build_type = 'debug'
    await config.save()

    return Make(build_path)

@pytest.mark.asyncio
async def test_catch2_build():
    
    make = await prepare_make()
    await make.initialize()
    catch2, = Target.get('catch2')
    await catch2.initialize()

    assert not catch2.output.exists()
    await catch2.build()
    assert catch2.output.exists()
    modified_at = catch2.output.modification_time
