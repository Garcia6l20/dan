from pymake.logging import Logging


class AsyncExecutable(Logging):
    async def execute(self, *args): ...


class Test:
    def __init__(self, makefile, executable: AsyncExecutable, name: str = None, *args) -> None:
        self.name = name or executable.name
        self.fullname = f'{makefile.fullname}.{self.name}'
        self.executable = executable
        self.args = list(args)

    async def __call__(self):
        out, err, rc = await self.executable.execute(*self.args, pipe=True, no_raise=True)
        if rc != 0:
            self.executable.error(
                f'Test failed !\nstdout: {out}\nstderr: {err}')
            return False
        else:
            self.executable.info(f'Test succeed !')
            return True
