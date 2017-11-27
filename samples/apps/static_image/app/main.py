import sys
import logging

import numpy
import cv2

from flipdisc import particle, util, image
from flipdisc.framework.app import Application
from flipdisc.framework.common import REDIS_KEYS


class MyApp(Application):

    def __init__(self, *args, **kwargs):
        super(MyApp, self).__init__(*args, **kwargs)
        self.setup()

    def setup(self):
        self.width = self.config['output_stream']['width']
        self.height = self.config['output_stream']['height']
        self.current_bg = ('', -1)

        self.emitter = particle.Emitter()
        self.emitter.set_size(self.height, self.width)


def update_app(app):
    bg_cfg = app.config['settings']
    bg_name = bg_cfg['image']
    bg_thresh = bg_cfg['threshold']
    bg_resize_mode = bg_cfg.get('resize_mode', 'stretch')
    bg_resize_factor = bg_cfg.get('resize_factor', 1)

    if app.current_bg != (bg_name, bg_thresh, bg_resize_mode, bg_resize_factor):
        if not bg_name:
            # Clear particles.
            app.emitter.clear()
        else:
            # Load image and convert to binary.
            bg_area = numpy.zeros((app.height, app.width), dtype=numpy.uint8)

            gray = cv2.imread(bg_name, cv2.IMREAD_GRAYSCALE)
            if not hasattr(image, 'resize_%s' % bg_resize_mode):
                resize_func = image.resize_stretch
                app.log.warning('resize_mode %s not available, using stretch', bg_resize_mode)
                bg_cfg['resize_mode'] = 'stretch'
            else:
                resize_func = getattr(image, 'resize_%s' % bg_resize_mode)

            if resize_func == getattr(image, 'resize_factor', None):
                contain_h = float(app.height) / gray.shape[0]
                contain_w = float(app.width)  / gray.shape[1]
                contain_scale = min(contain_h, contain_w)
                resize_factor = contain_scale * bg_resize_factor
                gray = resize_func(gray, bg_area, resize_factor, resize_factor)
            else:
                gray = resize_func(gray, (app.width, app.height),
                        interpolation=cv2.INTER_AREA)

            if bg_thresh >= 0:
                bg_area[gray <= bg_thresh] = 0
                bg_area[gray > bg_thresh] = 255
            else:
                bg_area = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

            if bg_area is not None:
                # Convert image to particles.
                util.image_to_particles(app.emitter, bg_area)

        app.current_bg = (bg_name, bg_thresh, bg_resize_mode, bg_resize_factor)


def draw_and_send(app):
    result = numpy.zeros((app.height, app.width), numpy.uint8)

    # Draw particles.
    app.emitter.update()
    bg_invert = app.config['settings']['invert']
    if not bg_invert:
        app.emitter.draw(result)
    else:
        result.fill(255)
        app.emitter.draw(result, 0)

    app.send_output(result)


def channel_update(app, channel, update):
    if channel == REDIS_KEYS.SYS_OUTPUT_CHANNEL:
        app.setup()


def main(cfg_path):
    app = MyApp("static_image", cfg_path, setup_input=False, verbose=True)
    app.log = logging.getLogger(__name__)
    app.set_redis_callback(channel_update)
    app.add_periodic_callback(draw_and_send, 1/30.)
    app.add_periodic_callback(update_app, 1/60.)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.cleanup()


if __name__ == "__main__":
    main(sys.argv[1])
