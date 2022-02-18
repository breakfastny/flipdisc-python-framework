import os
from setuptools import setup, Extension


def get_numpy_include():
    """Helper for lazy-importing numpy to get includes"""
    import numpy

    return numpy.get_include()


setup(
    name="flipdisc",
    version="0.5.4",
    url="https://github.com/breakfastny/flipdisc-python-framework",
    packages=["flipdisc", "flipdisc.framework"],
    package_data={
        "flipdisc.framework": ["*.json"],
    },
    setup_requires=["cffi>=1.0.0", "cython"],
    cffi_modules=["flipdisc/build_particle.py:ffibuilder"],
    install_requires=[
        "cffi>=1.0.0",
        "numpy>=1.12.1",
        "pyzmq>=16.0.2",
        "tornado>=4.4.2",
        "toredis>=0.1.2",
        "jsonschema>=2.6.0",
    ],
    ext_modules=[
        Extension(
            "flipdisc.binarize",
            ["flipdisc/binarize.pyx"],
            extra_compile_args=["-g0", "-O2"],
            include_dirs=(f() for f in [get_numpy_include]),
        ),
    ],
    zip_safe=False,
)
