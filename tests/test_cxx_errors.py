from pathlib import Path
from tests import PyMakeBaseTest

from dan.cxx.toolchain import CompilationFailure, LinkageFailure
from dan.core.asyncio import ExceptionGroup


base_path = Path(__file__).parent / 'errors' / 'cxx'

class CXXSimpleErrors(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__(methodName=methodName, source_path=base_path)

    async def test_invalid_syntax(self):
        async with self.section('invalid-syntax', targets=['InvalidSyntax'], clean=True, diags=True) as make:
            try:
                await make.build()
                self.fail('No exception raised')
            except ExceptionGroup as err:
                # Note: CompilationFailure always within a group, because all objects are built in parallel
                self.assertEqual(len(err.errors), 1, 'Error not detected')
                err : CompilationFailure = err.errors.pop()
                self.assertTrue(isinstance(err, CompilationFailure))
                self.assertEqual(err.sourcefile.name, 'invalid-syntax.cpp')
                diags = list(err.diags)
                self.assertGreaterEqual(len(diags), 1, 'Error not detected')
            except RuntimeError as err:
                self.fail(f'Wrong exception raised: {err} ({type(err)})')

    async def test_no_main(self):
        async with self.section('no-main', targets=['NoMain'], clean=True, diags=True) as make:
            try:
                await make.build()
                self.fail('No exception raised')
            except LinkageFailure as err:
                diags = list(err.diags)
                self.assertEqual(len(diags), 1, 'Error not detected')
                diag = diags[0]
                if make.toolchain.type == 'msvc':
                    self.assertTrue(diag.code == 'LNK1561')
                else:
                    self.assertTrue('undefined reference' in diag.message)
                    self.assertTrue('main' in diag.message)
            except RuntimeError:
                self.fail('Wrong exception raised')

    async def test_undefined_reference(self):
        async with self.section('undefined-reference', targets=['UndefinedReference'], clean=True, diags=True) as make:
            try:
                await make.build()
                self.fail('No exception raised')
            except LinkageFailure as err:
                diags = err.diags
                self.assertEqual(len(diags), 2, 'Error not detected')
                undefined_vars = ['undefined1', 'undefined2']
                for diag in diags:
                    # self.assertTrue(Path(error.filename).name == 'undefined-reference.cpp')
                    if make.toolchain.type == 'msvc':
                        self.assertTrue(diag.code == 'LNK2001')
                    else:
                        # self.assertTrue(diag.function == 'main')
                        self.assertTrue('undefined reference' in diag.message)
                    # Note: may not be ordered
                    self.assertTrue(any(var_name in diag.message for var_name in undefined_vars))
            except RuntimeError:
                self.fail('Wrong exception raised')
