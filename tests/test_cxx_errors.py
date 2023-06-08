from pathlib import Path
from tests import PyMakeBaseTest

from dan.cxx.toolchain import CompilationFailure, LinkageFailure
from dan.core.asyncio import ExceptionGroup


base_path = Path(__file__).parent / 'errors'

class CXXSimpleErrors(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__(methodName=methodName, source_path=base_path / 'simple')

    async def test_invalid_syntax(self):
        async with self.section('invalid-syntax', targets=['InvalidSyntax'], clean=True) as make:
            try:
                await make.build()
                self.fail('No exception raised')
            except ExceptionGroup as err:
                # Note: CompilationFailure always within a group, because all objects are built in parallel
                self.assertEqual(len(err.errors), 1, 'Error not detected')
                err = err.errors.pop()
                self.assertTrue(isinstance(err, CompilationFailure))
                errors = list(err.errors)
                self.assertGreaterEqual(len(errors), 1, 'Error not detected')
            except RuntimeError as err:
                self.fail(f'Wrong exception raised: {err} ({type(err)})')

    async def test_no_main(self):
        async with self.section('no-main', targets=['NoMain'], clean=True) as make:
            try:
                await make.build()
                self.fail('No exception raised')
            except LinkageFailure as err:
                errors = list(err.errors)
                self.assertEqual(len(errors), 1, 'Error not detected')
                error = errors[0]
                self.assertTrue(error.is_global)
                if make.toolchain.type == 'msvc':
                    self.assertTrue(error.code == 'LNK1561')
                else:
                    self.assertTrue('undefined reference' in error.message)
                    self.assertTrue('main' in error.message)
            except RuntimeError:
                self.fail('Wrong exception raised')

    async def test_undefined_reference(self):
        async with self.section('undefined-reference', targets=['UndefinedReference'], clean=True) as make:
            try:
                await make.build()
                self.fail('No exception raised')
            except LinkageFailure as err:
                errors = list(err.errors)
                self.assertEqual(len(errors), 2, 'Error not detected')
                undefined_vars = ['undefined1', 'undefined2']
                for error in errors:
                    self.assertTrue(not error.is_global)
                    self.assertTrue(Path(error.filename).name == 'undefined-reference.cpp')
                    if make.toolchain.type == 'msvc':
                        self.assertTrue(error.code == 'LNK2001')
                    else:
                        self.assertTrue(error.function == 'main')
                        self.assertTrue('undefined reference' in error.message)
                    # Note: may not be ordered
                    self.assertTrue(any(var_name in error.message for var_name in undefined_vars))
            except RuntimeError:
                self.fail('Wrong exception raised')
