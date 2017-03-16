import time

from flipdisc._particle import lib

__all__ = ["Emitter"]


class Emitter:
    def __init__(self, start_time=True):
        self._ctx = lib.emitter_context()
        if start_time:
            self._start = time.time()
        else:
            self._start = None

    def __del__(self):
        lib.emitter_free(self._ctx)

    def update(self):
        if self._start is not None:
            self.update_elapsed_time(time.time() - self._start)
        lib.emitter_update(self._ctx)

    def update_elapsed_time(self, t):
        pctx = self._ctx.pctx
        pctx.elapsed_time = t

    def set_size(self, height, width):
        pctx = self._ctx.pctx
        pctx.size.x = height
        pctx.size.y = width

    def clear(self):
        lib.emitter_remove_all(self._ctx)

    def add_particle(self, position):
        return lib.emitter_add_particle(self._ctx, position)

    def add_force(self, position, velocity):
        lib.emitter_add_force(self._ctx, position, velocity)

    def draw(self, mat, value=255):
        height, width = mat.shape

        pctx = self._ctx.pctx
        for i in xrange(pctx.num_particles):
            particle = pctx.particles[i]
            position = particle.position.x, particle.position.y
            intp = int(round(position[0])), int(round(position[1]))
            if intp[0] < height and intp[1] < width and intp[0] > 0 and intp[1] > 0:
                mat[intp] = value
