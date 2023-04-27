import unittest

from pymake.core.runners import cmdline2list
from subprocess import list2cmdline



class CmdLine2ListTests(unittest.TestCase):

    def assert2Way(self, test, expected=None):
        tmp = list2cmdline(test)
        back = cmdline2list(tmp)
        if expected:
            self.assertEqual(test, expected)
        else:
            self.assertEqual(test, back)

    def test_basic(self):
        self.assert2Way(['hello', 'world'])
        self.assert2Way(['hello world'])
        tmp = cmdline2list('gcc -I"C:\\\\Program files"')
        self.assertEqual(tmp, ['gcc', '-IC:\\\\Program files'])
        back = list2cmdline(tmp)
        self.assertEqual(back, 'gcc "-IC:\\\\Program files"')
        self.assert2Way(['\"hello\" world'])


