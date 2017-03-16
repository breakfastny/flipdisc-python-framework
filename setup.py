from setuptools import setup

setup(
    name='flipdisc',
    version='0.0.1',
    packages=["flipdisc"],
    setup_requires=["cffi>=1.0.0"],
    cffi_modules=["build_particle.py:ffibuilder"],
    install_requires=["cffi>=1.0.0"],
)
