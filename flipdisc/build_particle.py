import os

from cffi import FFI

FDL_PATHS = []
if 'FDL_INCLUDE_DIR' in os.environ:
    FDL_PATHS.append(os.environ['FDL_INCLUDE_DIR'])
else:
    FDL_PATHS.append('/usr/local/include/fdl')
    FDL_PATHS.append('/usr/include/fdl')


def search_particle_h():
    for p in FDL_PATHS:
        check = os.path.join(p, 'particle.h')
        if os.path.exists(p) and os.path.exists(check):
            return check

    raise SystemExit('** ERROR: particle.h not found at %s' % (','.join(FDL_PATHS)))


ffibuilder = FFI()
ffibuilder.set_source('flipdisc._particle',
        '#include "fdl/particle.h"',
        libraries=['fparticle'])

raw_cdef = open(search_particle_h()).read()
# Skip includes and other things. This assumes the first definition
# in particle.h starts with a struct.
raw_start = raw_cdef.find('struct ')
raw_end = raw_cdef.find('#ifdef __cplusplus', raw_start + 1)
ffibuilder.cdef(raw_cdef[raw_start:raw_end])

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
