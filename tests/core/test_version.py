import unittest

from dan.core.version import Version
import random


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
        
        self.assertTrue(Version('0.11.0') < Version('10.0.0'))
        self.assertTrue(Version('9.1.0') < Version('10.0.0'))

    def test_sorting(self):
        values = [
            '0.11.0',
            '5.0.0',
            '6.1.2',
            '8.1.1',
            '9.0.0',
            '9.1.0',
            '10.0.0',
        ]
        expected_versions = [Version(v) for v in values]
        unsorted_versions = [Version(v) for v in values]
        random.shuffle(unsorted_versions)
        sorted_versions = sorted(unsorted_versions)
        self.assertEqual(expected_versions, sorted_versions)
