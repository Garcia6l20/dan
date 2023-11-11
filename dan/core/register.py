class MakefileRegister:
    
    __makefile = None

    def __init_subclass__(cls, *args, internal=False, **kwargs):
        if not internal:
            from dan.core.include import context
            cls.__makefile = context.current
            cls.__makefile.register(cls)

    @classmethod
    def get_static_makefile(cls):
        return cls.__makefile

    @property
    def makefile(self) -> 'MakeFile':
        return self.__makefile
    
    @property
    def context(self):
        return self.__makefile.context
    
    @makefile.setter
    def makefile(self, value):
        assert self.__makefile is None, 'makefile should be set once'
        self.__makefile = value
