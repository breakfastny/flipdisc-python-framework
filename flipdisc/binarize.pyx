import numpy as np
cimport cython
cimport numpy as np

DTYPE = np.float

ctypedef np.float_t DTYPE_t


@cython.boundscheck(False)
@cython.wraparound(False)
def dither_floydsteinberg(np.ndarray[DTYPE_t, ndim=2] im):
    """
          p   7
      3   5   1

    1/16
    """
    assert im.dtype == DTYPE

    cdef int rows = im.shape[0]
    cdef int cols = im.shape[1]
    cdef DTYPE_t old, error
    cdef int i, j

    for i in range(rows):
        for j in range(cols):
            old = im[i, j]
            im[i, j] = 255 if old > 127 else 0
            error = old - im[i, j]

            if j + 1 < cols:
                im[i    , j + 1] = im[i    , j + 1] + error * (7/16.)
            if i + 1 < rows:
                if j - 1 >= 0:
                    im[i + 1, j - 1] = im[i + 1, j - 1] + error * (3/16.)
                im[i + 1, j    ] = im[i + 1, j    ] + error * (5/16.)
                if j + 1 < cols:
                    im[i + 1, j + 1] = im[i + 1, j + 1] + error * (1/16.)


@cython.boundscheck(False)
@cython.wraparound(False)
def dither_atkinson(np.ndarray[DTYPE_t, ndim=2] im):
    """
          p   1   1
      1   1   1
          1

    1/8 (reduced color bleed)
    """
    assert im.dtype == DTYPE

    cdef int rows = im.shape[0]
    cdef int cols = im.shape[1]
    cdef DTYPE_t old, error
    cdef int i, j

    for i in range(rows):
        for j in range(cols):
            old = im[i, j]
            im[i, j] = 255 if old > 127 else 0
            error = (old - im[i, j]) / 8.

            if j + 1 < cols:
                im[i, j + 1] = im[i, j + 1] + error
                if j + 2 < cols:
                    im[i, j + 2] = im[i, j + 2] + error
            if i + 1 < rows:
                if j - 1 >= 0:
                    im[i + 1, j - 1] = im[i + 1, j - 1] + error
                im[i + 1, j] = im[i + 1, j] + error
                if j + 1 < cols:
                    im[i + 1, j + 1] = im[i + 1, j + 1] + error
                if i + 2 < rows:
                    im[i + 2, j] = im[i + 2, j] + error
