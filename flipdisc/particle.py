from flipdisc._particle import lib, ffi

__all__ = ["Emitter"]

_EMITTER_KEYS = {
    'input_radius': float,
    'input_amplitude': float,
}
_PARTICLE_KEYS = {
    'friction': float,
    'gravity': float,
    'gravity_acceleration': float,
    'gravity_enabled': bool,
    'restitution': float,
    'offscreen_delay_max': float,
    'offscreen_delay_min': float,
    'spawn_radius_max': float,
    'spawn_radius_min': float,
    'speed': float,
}
_LIMIT_TO_01 = frozenset(['friction', 'restitution'])
_LIMIT_TO_0 = frozenset(['gravity'])


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

    def get_settings(self):
        pctx = self._ctx.pctx
        settings = {
            'size': {'x': pctx.size.x, 'y': pctx.size.y}
        }
        for name in _PARTICLE_KEYS:
            settings[name] = getattr(pctx, name)
        return settings

    def set_setting(self, name, value):
        if name in _EMITTER_KEYS:
            value = _EMITTER_KEYS[name](value)
            if value <= 0:
                raise ValueError('"%s" must be greater than 0')
            setattr(self._ctx, name, value)
            return

        pctx = self._ctx.pctx
        if name in _PARTICLE_KEYS:
            value = _PARTICLE_KEYS[name](value)
            if name in _LIMIT_TO_01 and (value < 0 or value > 1):
                raise ValueError('"%s" must be between 0 and 1' % name)
            if name in _LIMIT_TO_0 and value < 0:
                raise ValueError('"%s" must be greater or equal to 0' % name)
            setattr(pctx, name, value)
            return

        raise KeyError('Unknown setting "%s"' % name)

    def clear(self):
        lib.emitter_remove_all(self._ctx)

    def add_particle(self, position):
        return lib.emitter_add_particle(self._ctx, position)

    def add_force(self, position, velocity):
        lib.emitter_add_force(self._ctx, position, velocity)

    def draw(self, mat, value=255):
        height, width = mat.shape
        arr = ffi.cast('uint8_t*', ffi.from_buffer(mat))
        lib.particles_draw(self._ctx.pctx, value, arr, width, height)
