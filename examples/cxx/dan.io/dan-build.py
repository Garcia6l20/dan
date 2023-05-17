import hashlib
from dan import requires
from dan.cxx import Executable
from dan.testing import Test, Case

catch2, = requires('catch2 = 3')

@catch2.discover_tests
class UseCatch2(Executable):
    sources = 'test_catch2.cpp',
    dependencies = [
        catch2,
        'spdlog >= 1.11',
    ]


class TestSpdlog(Test, Executable):
    name = 'test-spdlog'
    sources = 'test_spdlog.cpp',
    private_includes= '.',
    dependencies = (
        'spdlog = 1',
        'fmt = 9',
    )


class TestMbedTLS(Test, Executable):
    name = 'test-mbedtls'
    sources = 'test_mbedtls.cpp',
    dependencies = (
        'mbedtls:mbedcrypto = 3',
        'fmt = 9',
    )

    def make_expected_result(case: Case):
        sha = hashlib.sha256()
        for arg in case.args:
            sha.update(arg.encode())
        return f'SHA-256: {sha.hexdigest()}'

    cases = [
        Case('hello', 'hello', expected_output=make_expected_result),
        Case('hello-dan', 'hello', 'dan', expected_output=make_expected_result),
    ]
