from pymake.conan import Requirements, Package

boost = Package('boost', '1.81.0',
                options={
                    'header_only': True
                })

Requirements(
    'zlib/1.2.11',
    boost
)
