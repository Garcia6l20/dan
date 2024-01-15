class MakefileRegister:
    
    makefile = None

    def __init_subclass__(cls, *args, internal=False, **kwargs):
        if not internal:
            from dan.core.include import context
            cls.makefile = context.current
            cls.makefile.register(cls)

    @classmethod
    def get_static_makefile(cls):
        return cls.makefile
    
    @property
    def context(self):
        return self.makefile.context
