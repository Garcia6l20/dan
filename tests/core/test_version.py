import unittest

from pymake.core.version import Version


class VersionTests(unittest.TestCase):

    def test_basic(self):
        v = Version('1.0.0')
        self.assertEqual(str(v), '1.0.0')
        self.assertEqual(v, '1.0.0')
        self.assertEqual(v, '1')
        self.assertTrue(v >= '1')
        self.assertTrue(v >= '1.0.0')
        self.assertTrue(v < '2.1.42')

        
        v = Version('4.2.3')
        self.assertTrue(v > '3.2.2')
        self.assertTrue(v < '4.2.4')
        self.assertTrue(v == '4.2.3')

        v = Version('4.2.0')
        self.assertTrue(v == '4.2')
