from pathlib import Path
from dan.core.include import MakeFileError
from tests import PyMakeBaseTest

base_path = Path(__file__).parent / 'errors' / 'python'

class PythonErrors(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__(methodName=methodName, source_path=base_path)

    async def test_import_error(self):
        async with self.section('import_error', targets=['InvalidSyntax'], subdir='import_error', clean=True, diags=True, init=False) as make:
            try:
                await make.initialize()
                self.fail('MakeFileError should have been raised')
            except MakeFileError:
                diags = make.diagnostics
                self.assertEqual(len(diags), 1)
                filename = str(self.source_path / 'import_error' / 'dan-build.py')
                self.assertTrue(filename in diags)
                self.assertEqual(len(diags[filename]), 1)
                self.assertEqual(diags[filename][0].message, "No module named 'not_a_module'")

    async def test_all_errors(self):
        async with self.section('import_error', targets=['InvalidSyntax'], clean=True, diags=True, init=False) as make:
            try:
                await make.initialize()
                self.fail('MakeFileError should have been raised')
            except MakeFileError:
                diags = make.diagnostics
                self.assertEqual(len(diags), 2)
