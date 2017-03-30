import os
from setuptools import setup, Extension

if os.getenv('USE_CYTHON', '0').lower() in ('0', 'f', 'false'):
    CYTHON_BUILD = None
    binarize_src = 'flipdisc/binarize.c'
else:
    from Cython.Distutils import build_ext
    CYTHON_BUILD = build_ext
    binarize_src = 'flipdisc/binarize.pyx'
binarize_ext = Extension('flipdisc.binarize', [binarize_src])


def run_setup(build_cext):
    extra = {}
    if build_cext:
        import numpy
        extra = {'ext_modules': [binarize_ext]}
        extra['include_dirs'] = [numpy.get_include()]
        if CYTHON_BUILD:
            extra['cmdclass'] = {'build_ext': CYTHON_BUILD}

    setup(
        name='flipdisc',
        version='0.2.2',
        packages=["flipdisc", "flipdisc.framework"],
        setup_requires=["cffi>=1.0.0"],
        cffi_modules=["build_particle.py:ffibuilder"],
        install_requires=["cffi>=1.0.0"],
        zip_safe=False,
        extras_require={
            'app_framework': [
                'numpy==1.12.1',
                'pyzmq==16.0.2',
                'tornado==4.4.2',
                'toredis==0.1.2',
                'attrdict==2.0.0',
            ]
        },
        **extra
    )

try:
    import numpy
except ImportError:
    run_setup(False)

try:
    run_setup(True)
except Exception as err:
    print("\n>> ERROR: %s" % err)
    print("\n** WARNING: flipdisc.binarize not available")