import os

from cffi import FFI

HERE = os.path.dirname(os.path.abspath(__file__))
FDL_PATH = os.getenv('FDL_INCLUDE_DIR', '/usr/local/include/fdl')
PARTICLE_H = os.path.join(FDL_PATH, 'particle.h')
if not os.path.exists(FDL_PATH):
    raise SystemExit('** ERROR: FDL_INCLUDE_DIR "%s" does not exist' % FDL_PATH)
if not os.path.exists(PARTICLE_H):
    raise SystemExit('** ERROR: FDL_INCLUDE_DIR does not contain "particle.h"')


ffibuilder = FFI()
ffibuilder.set_source('flipdisc._particle',
        '#include "fdl/particle.h"',
        libraries=['fparticle'])

raw_cdef = open(PARTICLE_H).read()
# Skip includes and other things. This assumes the first definition
# in particle.h starts with a struct.
raw_start = raw_cdef.find('struct ')
raw_end = raw_cdef.find('#ifdef __cplusplus', raw_start + 1)
ffibuilder.cdef(raw_cdef[raw_start:raw_end])

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
