class BaseDecorator:
    """ Base class helper for decorator classes that might be used on instance methods.
    """
    is_method: bool = False

    class _GetBoundedInstanceWrapper:
        """ Callable that store wrapped class instance and decorator instance. """

        def __init__(self, decorator_instance, wrapped_instance):
            self.decorator_instance = decorator_instance
            self.wrapped_instance = wrapped_instance

        def __call__(self, *args, **kwargs):
            return self.decorator_instance(self.wrapped_instance, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self.decorator_instance, name)

    def __get__(self, wrapped_instance, _owner):
        """ For object method decoration.
            It will detect __get__ as descriptor protocol.
            So __get__ should return the actual method.
        """
        # pass decorator instance and decorated object instance
        self.is_method = True
        return self._GetBoundedInstanceWrapper(self, wrapped_instance)
