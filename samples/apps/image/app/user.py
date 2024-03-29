import sys
import time
import logging

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
        filter_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self.opening = lambda im: cv2.morphologyEx(im, cv2.MORPH_OPEN, filter_kernel)
        self.closing = lambda im: cv2.morphologyEx(im, cv2.MORPH_CLOSE, filter_kernel)

        self.optflow = optical_flow.OpticalFlow(**self.config['settings']['optical_flow'])
        self.emitter = particle.Emitter()
        self.emitter.set_size(self.height, self.width)


def process_frame(app, frame_num, depth, bgr):
    if not app.config['settings']['run']:
        draw_and_send(app)
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
    trimmed = False
    if any((inp_cfg['trim_top'], inp_cfg['trim_right'],
            inp_cfg['trim_bottom'], inp_cfg['trim_left'])):
        gray_height, gray_width = gray.shape
        gray = gray[inp_cfg['trim_top']:gray_height - inp_cfg['trim_bottom'],
                    inp_cfg['trim_left']:gray_width - inp_cfg['trim_right']]
        trimmed = True
    # Resize
    resize_mode = inp_cfg.get('resize_mode')
    if not hasattr(image, 'resize_%s' % resize_mode):
        resize_func = image.resize_stretch
        app.log.warning('resize_mode %s not available, using stretch', resize_mode)
        inp_cfg['resize_mode'] = 'stretch'
    else:
        resize_func = getattr(image, 'resize_%s' % resize_mode)
    gray = resize_func(gray, (app.width, app.height), interpolation=cv2.INTER_NEAREST)
    # Binarize.
    user_threshold = inp_cfg['threshold']
    gray[gray > user_threshold] = 255
    gray[gray <= user_threshold] = 0
    # Clear mask if there are too few active points.
    cleared = False
    filter_depth_threshold = inp_cfg.get('filter_threshold', 0)
    clear_threshold = gray.shape[0] * gray.shape[1] * (filter_depth_threshold / 100.0)
    if filter_depth_threshold and numpy.count_nonzero(gray) < clear_threshold:
        gray.fill(0)
        cleared = True
    app.last_user = gray.copy()

    user_mask = numpy.zeros(depth.shape, gray.dtype)
    if not cleared:
        user_mask[(depth >= depth_min) & (depth <= depth_max)] = 255
    if trimmed:
        m_height, m_width = user_mask.shape
        user_mask = user_mask[inp_cfg['trim_top']:m_height - inp_cfg['trim_bottom'],
                              inp_cfg['trim_left']:m_width - inp_cfg['trim_right']]
    user_mask = resize_func(user_mask, (app.width, app.height), interpolation=cv2.INTER_NEAREST)
    app.last_user_mask = user_mask

    update_flow(app)
    draw_and_send(app)
    app.last_frame_at = time.time()


def update_flow_30(app):
    # Render the current particles if the user display is disabled.
    inp_cfg = app.config['settings']['display']
    if not inp_cfg['enabled'] or time.time() - app.last_frame_at >= 0.3:
        update_flow(app)
        draw_and_send(app)


def update_flow(app):
    if not app.config['settings']['run']:
        draw_and_send(app)
        return

    if app.last_user_mask is not None:
        if app.config['settings']['interactive']:
            app.optflow.update(app.last_user_mask, app.emitter)

    app.emitter.update()


def _image_to_particles(emitter, im, transition=True):
    pctx = emitter._ctx.pctx
    prev_max, prev_min = pctx.spawn_radius_max, pctx.spawn_radius_min
    if not transition:
        pctx.spawn_radius_max, pctx.spawn_radius_min = 0, 0
    util.image_to_particles(emitter, im)
    pctx.spawn_radius_max, pctx.spawn_radius_min = prev_max, prev_min


def update_app(app):
    if not app.config['settings']['run']:
        return

    bg_cfg = app.config['settings']['background']
    bg_invert = bg_cfg['invert']
    bg_invert_particles = bg_cfg.get('invert_particles', False)
    bg_name = bg_cfg['image']
    bg_thresh = bg_cfg['threshold']
    bg_resize_mode = bg_cfg.get('resize_mode', 'stretch')
    bg_resize_factor = float(bg_cfg.get('resize_factor', 1))
    bg_transition = app.config['settings']['background'].get('transition', True)

    if app.current_bg != (bg_invert, bg_invert_particles, bg_name, bg_thresh, bg_resize_mode, bg_resize_factor):
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

            if bg_invert_particles:
                bg_area = ~bg_area

            if bg_invert:
                bg_area = ~bg_area

            if bg_area is not None:
                # Convert image to particles.
                _image_to_particles(app.emitter, bg_area, transition=bg_transition)

        app.current_bg = (bg_invert, bg_invert_particles, bg_name, bg_thresh, bg_resize_mode, bg_resize_factor)

    curr_particles = app.config['settings']['particles']
    if curr_particles == app.particles_settings:
        return
    app.particles_settings = curr_particles.copy()
    for key, value in list(app.particles_settings.items()):
        if key == 'reverse':
            app.optflow.update_settings(reverse=value)
            continue
        app.emitter.set_setting(key, value)


def draw_and_send(app):
    result = numpy.zeros((app.height, app.width), numpy.uint8)
    if not app.config['settings']['run']:
        app.send_output(result)
        # XXX possibly stop sending blank frames after sending one.
        return

    # Draw particles.
    bg_invert_particles = app.config['settings']['background']['invert_particles']
    if not bg_invert_particles:
        app.emitter.draw(result)
    else:
        result.fill(255)
        app.emitter.draw(result, 0)

    # Draw the user.
    if app.last_user is not None and app.last_user_mask is not None:
        invert_user = app.config['settings']['display']['invert']
        # Erase any points that belong to the user.
        result[app.last_user_mask != 0] = 0 if not invert_user else 255
        # Draw the thresholded user.
        result[app.last_user != 0] = 255 if not invert_user else 0

        app.last_user_mask = app.last_user = None

    app.send_output(result)


def channel_update(app, channel, update):
    if channel == REDIS_KEYS.SYS_OUTPUT_CHANNEL:
        app.setup()


def main(cfg_path):
    app = MyApp("image", cfg_path, verbose=True, setup_input=False)
    app.log = logging.getLogger(__name__)
    app.setup_input(watermark=60)
    app.set_input_callback(process_frame)
    app.set_redis_callback(channel_update)
    app.last_frame_at = time.time()
    app.add_periodic_callback(update_flow_30, 1/30.)
    app.add_periodic_callback(update_app, 1/60.)
    # Ensure the initial frame contains the logo.
    update_app(app)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.cleanup()


if __name__ == "__main__":
    main(sys.argv[1])
