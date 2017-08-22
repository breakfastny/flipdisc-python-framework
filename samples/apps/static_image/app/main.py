import sys
import logging

import numpy

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
    if app.current_bg != (bg_name, bg_thresh):
        if not bg_name:
            # Clear particles.
            app.emitter.clear()
        else:
            # Load image and convert to binary.
            bg_area = image.load_image(bg_name, (app.height, app.width),
                    binarize=bg_thresh, padding=0)
            if bg_area is not None:
                # Convert image to particles.
                util.image_to_particles(app.emitter, bg_area)

        app.current_bg = (bg_name, bg_thresh)


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
    app = MyApp("static_image", cfg_path, verbose=True)
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
