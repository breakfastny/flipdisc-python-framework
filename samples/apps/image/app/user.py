import sys

import numpy
import cv2

from flipdisc import particle, optical_flow, util, image
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
        self.particles_settings = None
        self.last_user_mask = None
        self.last_user = None

        self.optflow = optical_flow.OpticalFlow(**self.config['settings']['optical_flow'])
        self.emitter = particle.Emitter()
        self.emitter.set_size(self.height, self.width)


def process_frame(app, frame_num, depth, bgr):
    if not app.config['settings']['run']:
        return

    # Get current settings
    inp_cfg = app.config['settings']['display']
    if not inp_cfg['enabled']:
        return
    depth_min = inp_cfg['depth_min_threshold']
    depth_max = inp_cfg['depth_max_threshold']

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    depth = util.flip(depth, inp_cfg['flip_mirror'], inp_cfg['flip_upsidedown'])
    gray = util.flip(gray, inp_cfg['flip_mirror'], inp_cfg['flip_upsidedown'])

    # Apply the depth threholds in the color image.
    gray[(depth < depth_min) | (depth > depth_max)] = 0
    # Crop based on the trim settings.
    if any((inp_cfg['trim_top'], inp_cfg['trim_right'],
            inp_cfg['trim_bottom'], inp_cfg['trim_left'])):
        gray_height, gray_width = gray.shape
        gray = gray[inp_cfg['trim_top']:gray_height - inp_cfg['trim_bottom'],
                    inp_cfg['trim_left']:gray_width - inp_cfg['trim_right']]
    # Resize
    gray = cv2.resize(gray, (app.width, app.height), interpolation=cv2.INTER_NEAREST)
    # Binarize.
    user_threshold = inp_cfg['threshold']
    gray[gray > user_threshold] = 255
    gray[gray <= user_threshold] = 0
    app.last_user = gray.copy()

    user_mask = numpy.zeros(depth.shape, gray.dtype)
    user_mask[(depth >= depth_min) & (depth <= depth_max)] = 255
    user_mask = cv2.resize(user_mask, (app.width, app.height), interpolation=cv2.INTER_NEAREST)
    app.last_user_mask = user_mask


def update_flow(app):
    if not app.config['settings']['run']:
        return

    if app.last_user_mask is not None:
        if app.config['settings']['interactive']:
            app.optflow.update(app.last_user_mask, app.emitter)

    app.emitter.update()


def update_app(app):
    if not app.config['settings']['run']:
        return

    bg_cfg = app.config['settings']['background']
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

    curr_particles = app.config['settings']['particles']
    if curr_particles == app.particles_settings:
        return
    app.particles_settings = curr_particles.copy()
    for key, value in app.particles_settings.items():
        app.emitter.set_setting(key, value)


def draw_and_send(app):
    result = numpy.zeros((app.height, app.width), numpy.uint8)
    if not app.config['settings']['run']:
        app.send_output(result)
        # XXX possibly stop sending blank frames after sending one.
        return

    # Draw particles.
    app.emitter.draw(result)

    # Draw the user.
    if app.last_user is not None and app.last_user_mask is not None:
        # Erase any points that belong to the user.
        result[app.last_user_mask != 0] = 0
        # Draw the thresholded user.
        result[app.last_user != 0] = 255

    app.send_output(result)


def channel_update(app, channel, update):
    if channel == REDIS_KEYS.SYS_OUTPUT_CHANNEL:
        app.setup()


def main(cfg_path):
    app = MyApp("image", cfg_path, verbose=True)
    app.set_input_callback(process_frame)
    app.set_redis_callback(channel_update)
    app.add_periodic_callback(update_flow, 1/30.)
    app.add_periodic_callback(update_app, 1/60.)
    app.add_periodic_callback(draw_and_send, 1/30.)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.cleanup()


if __name__ == "__main__":
    main(sys.argv[1])
