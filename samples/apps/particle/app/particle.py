import sys

import cv2
import numpy

from flipdisc import particle, util, image, optical_flow
from flipdisc.framework.app import Application
from flipdisc.framework.common import REDIS_KEYS


class MyApp(Application):

    def __init__(self, *args, **kwargs):
        super(MyApp, self).__init__(*args, **kwargs)
        self.setup()

    def setup(self):
        self.width = self.config['output_stream']['width']
        self.height = self.config['output_stream']['height']
        self.current_bg_name = ''

        self.ball_cfg = {'radius': 5, 'color': 255, 'thickness': -1}
        self.ball_position = numpy.array([0, 0])
        self.ball_direction = numpy.array([-1, -1])

        self.optflow = optical_flow.OpticalFlow(**self.config['settings']['optical_flow'])
        self.emitter = particle.Emitter()
        self.emitter.set_size(self.height, self.width)

    def move_ball(self):
        choice = lambda *x: numpy.random.choice(x)
        self.ball_position += self.ball_direction
        while (self.ball_position[0] > self.width or self.ball_position[0] < 0 or
                self.ball_position[1] > self.height or self.ball_position[1] < 0):
            # Out of bounds, get new direction.
            self.ball_position -= self.ball_direction
            self.ball_direction[choice(0, 1)] = choice(1, -1) * numpy.random.randint(1, 6)
            self.ball_position += self.ball_direction


def update_flow(app):
    if not app.config['settings']['run']:
        return

    result = numpy.zeros((app.height, app.width), numpy.uint8)

    if app.config['settings']['ball']['move']:
        app.move_ball()
    cv2.circle(result, tuple(app.ball_position), **app.ball_cfg)

    if app.config['settings']['interactive']:
        app.optflow.update(result, app.emitter)

    app.emitter.update()


def update_app(app):
    if not app.config['settings']['run']:
        return

    bg_name = app.config['settings']['background']['image']
    if app.current_bg_name != bg_name:
        if not bg_name:
            # Clear particles.
            app.emitter.clear()
        else:
            # Load new image and convert to binary.
            bg_area = image.load_image(bg_name, (app.height, app.width), binarize=-1, padding=0)
            if bg_area is not None:
                # Convert image to particles.
                util.image_to_particles(app.emitter, bg_area)

        app.current_bg_name = bg_name


def draw_and_send(app):
    result = numpy.zeros((app.height, app.width), numpy.uint8)
    if not app.config['settings']['run']:
        app.send_output(result)
        return

    # Draw particles.
    app.emitter.draw(result)

    # Draw the ball.
    if app.config['settings']['ball']['show']:
        cv2.circle(result, tuple(app.ball_position), **app.ball_cfg)

    app.send_output(result)


def channel_update(app, channel, update):
    if channel == REDIS_KEYS.SYS_OUTPUT_CHANNEL:
        app.setup()


def main(cfg_path):
    app = MyApp("particle", cfg_path, setup_input=False, verbose=True)
    app.set_redis_callback(channel_update)
    app.add_periodic_callback(update_flow, 1/30.)
    app.add_periodic_callback(update_app, 1/60.)
    app.add_periodic_callback(draw_and_send, 1/25.)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.cleanup()


if __name__ == "__main__":
    main(sys.argv[1])
