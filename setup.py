import os
from setuptools import setup, Extension


def get_numpy_include():
    """Helper for lazy-importing numpy to get includes"""
    import numpy

    return numpy.get_include()


setup(
    name="flipdisc",
    version="1.0.0",
    url="https://github.com/breakfastny/flipdisc-python-framework",
    packages=["flipdisc", "flipdisc.framework"],
    package_data={
        "flipdisc.framework": ["*.json"],
    },
    python_requires='>=3.7.*',
    setup_requires=[
        "cffi>=1.0.0",
        "cython",
        "numpy==1.21.6"
    ],
    cffi_modules=["flipdisc/build_particle.py:ffibuilder"],
    install_requires=[
        "cffi==1.15.0",
        "numpy==1.21.6",
        "jsonschema==4.6.0",
        "pyzmq==23.2.0",
        "redis==4.3.3"
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
