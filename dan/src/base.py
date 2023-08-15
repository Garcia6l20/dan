from dan.core.target import Target

class SourcesProvider(Target, internal=True):
    installed = False
    default = False

    async def available_versions(self):
        raise NotImplementedError(f'available_versions not implemented in {self.__class__.__name__}')
