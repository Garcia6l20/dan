from pathlib import Path
from tests import PyMakeBaseTest

from dan.cxx.base_toolchain import CompilationFailure, LinkageFailure


base_path = Path(__file__).parent / "errors" / "cxx"


class CXXSimpleErrors(PyMakeBaseTest):
    def __init__(self, methodName: str = None) -> None:
        super().__init__(methodName=methodName, source_path=base_path)

    async def test_invalid_syntax(self):
        async with self.section(
            "invalid-syntax", targets=["*.InvalidSyntax"], clean=True, diags=True
        ) as make:
            try:
                await make.build()
                self.fail("No exception raised")
            except* CompilationFailure as eg:
                # Note: CompilationFailure always within a group, because all objects are built in parallel
                self.assertEqual(len(eg.exceptions), 1, "Error not detected")
                err = eg.exceptions[0]
                self.assertEqual(err.sourcefile.name, "invalid-syntax.cpp")
                diags = list(err.diags)
                self.assertGreaterEqual(len(diags), 1, "Error not detected")
            except* Exception as eg:
                self.fail(f"Wrong exceptions raised: {eg.exceptions}")

    async def test_no_main(self):
        async with self.section(
            "no-main", targets=["*.NoMain"], clean=True, diags=True
        ) as make:
            try:
                await make.build()
                self.fail("No exception raised")
            except* LinkageFailure as eg:
                diags = list(eg.exceptions[0].diags)
                self.assertEqual(len(diags), 1, "Error not detected")
                diag = diags[0]
                if make.toolchain.type == "msvc":
                    self.assertTrue(diag.code == "LNK1561")
                else:
                    self.assertTrue("undefined reference" in diag.message)
                    self.assertTrue("main" in diag.message)
            except* Exception as eg:
                self.fail(f"Wrong exceptions raised: {eg.exceptions}")

    async def test_undefined_reference(self):
        async with self.section(
            "undefined-reference",
            targets=["*.UndefinedReference"],
            clean=True,
            diags=True,
        ) as make:
            try:
                await make.build()
                self.fail("No exception raised")
            except* LinkageFailure as eg:
                diags = list(eg.exceptions[0].diags)
                self.assertEqual(len(diags), 2, "Error not detected")
                undefined_vars = ["undefined1", "undefined2"]
                for diag in diags:
                    # self.assertTrue(Path(error.filename).name == 'undefined-reference.cpp')
                    if make.toolchain.type == "msvc":
                        self.assertTrue(diag.code == "LNK2001")
                    else:
                        # self.assertTrue(diag.function == 'main')
                        self.assertTrue("undefined reference" in diag.message)
                    # Note: may not be ordered
                    self.assertTrue(
                        any(var_name in diag.message for var_name in undefined_vars)
                    )
            except* Exception as eg:
                self.fail(f"Wrong exceptions raised: {eg.exceptions}")
