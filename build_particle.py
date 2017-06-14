import os

from cffi import FFI

HERE = os.path.dirname(os.path.abspath(__file__))

ffibuilder = FFI()

ffibuilder.set_source('flipdisc._particle',
        '#include "fdl/particle.h"',
        libraries=['fparticle'])

raw_cdef = open(os.path.join(HERE, '../flipdisc-core/src/fdl/particle.h')).read()
# Skip includes and other things. This assumes the first definition
# in particle.h starts with a struct.
raw_start = raw_cdef.find('struct ')
raw_end = raw_cdef.find('#ifdef __cplusplus', raw_start + 1)
ffibuilder.cdef(raw_cdef[raw_start:raw_end])

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
