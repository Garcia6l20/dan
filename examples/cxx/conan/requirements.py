from pymake.conan import Package

class Boost(Package):
    name = 'boost'
    version = '1.81.0'
    options={
        'header_only': True
    }

class Zlib(Package):
    name = 'zlib'
    version = '1.2.11'
