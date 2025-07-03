import os
from setuptools import setup, Extension


def get_numpy_include():
    """Helper for lazy-importing numpy to get includes"""
    import numpy

    return numpy.get_include()


setup(
    name="flipdisc",
    version="1.0.1",
    url="https://github.com/breakfastny/flipdisc-python-framework",
    packages=["flipdisc", "flipdisc.framework"],
    package_data={
        "flipdisc.framework": ["*.json"],
    },
    python_requires='>=3.12',
    setup_requires=[
        "cffi<2",
        "cython",
        "numpy<2"
    ],
    cffi_modules=["flipdisc/build_particle.py:ffibuilder"],
    install_requires=[
        "cffi<2",
        "numpy<2",
        "jsonschema<5",
        "pyzmq<28",
        "redis<6"
    ],
    ext_modules=[
        Extension(
            "flipdisc.binarize",
            ["flipdisc/binarize.pyx"],
            extra_compile_args=["-g0", "-O2", "-march=native"],
            include_dirs=(f() for f in [get_numpy_include]),
        ),
    ],
    zip_safe=False,
)
