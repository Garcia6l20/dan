from dan.core.register import Registry

import dan.core.typing as t

import dataclasses

def dataclass_from_dict(klass, d):
    try:
        fieldtypes = {f.name:f.type for f in dataclasses.fields(klass)}
        kwargs = dict()
        for f, v in d.items():
            typ = fieldtypes[f]
            if t.is_optional(typ):
                typ = t.get_args(typ)[0]
            kwargs[f] = typ(v) if v is not None else None
        return klass(**kwargs)
    except:
        return d # Not a dataclass field

class Lang:
    def __init__(self, name, file_extensions: list[str]) -> None:
        self.name = name
        self.file_extensions = file_extensions

class BaseToolchain(Registry, registry=True):
    final = False
    kind: str = None
    languages : list[Lang] = None
    SettingsClass: type = None
    __loaded = False
    __all = []

    def __init__(self, settings: t.Any):
        if settings is not None:
            if self.SettingsClass is not None and isinstance(settings, dict):
                self.settings = dataclass_from_dict(self.SettingsClass, settings)
            else:
                self.settings = settings
        

    @classmethod
    def load(cls):
        pass

    @classmethod
    def load_all(cls):
        if not cls.__loaded:
            for toolchain_cls in list(cls.registered_classes()):
                cls.__all.extend(toolchain_cls.load())
            cls.__loaded = True
        return cls.__all
