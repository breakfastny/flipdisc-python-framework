from flipdisc._particle import lib

__all__ = ["Emitter"]


class Emitter(object):

    def __init__(self, step=1./30):
        self._ctx = lib.emitter_context()
        self._step = step
        self._elapsed = 0.0

    def __del__(self):
        lib.emitter_free(self._ctx)

    def update(self, step=None):
        if step is None:
            step = self._step
        self._elapsed += step
        self.set_elapsed_time(self._elapsed)
        lib.emitter_update(self._ctx)

    def set_elapsed_time(self, elapsed):
        pctx = self._ctx.pctx
        pctx.elapsed_time = elapsed

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
