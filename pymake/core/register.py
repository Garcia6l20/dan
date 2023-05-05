class MakefileRegister:
    
    __makefile = None

    def __init_subclass__(cls, *args, internal=False, **kwargs):
        if not internal:
            from pymake.core.include import context
            cls.__makefile = context.current
            cls.__makefile.register(cls)
    
    @property
    def makefile(self):
        return self.__makefile
    
    @makefile.setter
    def makefile(self, value) -> 'MakeFile':
        assert self.__makefile is None, 'makefile should be set once'
        self.__makefile = value
