# sudo apt-get install libavdevice-dev libavfilter-dev portaudio19-dev
# requirements: pip install av pyaudio
import sys
import logging
from functools import partial

import cv2
import numpy
import pyaudio

from flipdisc.framework.common import REDIS_KEYS
from flipdisc.framework.app import Application
from flipdisc.binarize import dither_atkinson

from movie import Movie


def get_out_shape(app):
    return (
        app.config['output_stream']['width'],
        app.config['output_stream']['height']
    )


def render(app, img, ts, finished=False):
    if finished:
        app.finished = True
        app.log('finished video')
        return

    out_shape = get_out_shape(app)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, out_shape, interpolation=cv2.INTER_AREA)

    if app.config['settings']['binarize'] == 'dither':
        bin_result = gray.astype(numpy.float)
        dither_atkinson(bin_result)
        bin_result = bin_result.astype(numpy.uint8)
    else:
        bin_result = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    app.send_output(bin_result)
    # print("diff", time.time() - ts)


def update_app(app):
    if app.play != app.config['settings']['play']:
        app.play = app.config['settings']['play']
        if app.movie:
            if not app.play:
                app.movie.pause()
            else:
                app.movie.resume()

    curr_video = app.config['settings']['video']
    if app.current_video != curr_video or (app.finished and app.config['settings']['loop']):
        # New video file.
        app.log.info('switching from %s to %s', app.current_video, curr_video)
        app.finished = False
        if app.movie:
            app.movie.cleanup()
            app.movie = None
        if curr_video:
            app.movie = Movie(curr_video, desired_size=get_out_shape(app), audio=app.audio)
            app.movie.video_callback(partial(render, app))
            app.movie.start()
            if not app.play:
                app.movie.pause()
        app.current_video = curr_video


def channel_update(app, channel, update):
    if channel == REDIS_KEYS.APP_CHANNEL + app._app_rkey:
        if 'fd_cmd' in update and 'shutdown' in update['fd_cmd']:
            if app.movie:
                app.suspended = True
                app.movie.pause()
        elif 'play' in update and update['play']:
            if app.suspended and app.movie:
                app.movie.resume()
                app.suspended = False


def main(cfg_path):
    app = Application("video", cfg_path, verbose=True)
    app.log = logging.getLogger(__name__)
    app.audio = pyaudio.PyAudio()
    app.suspended = False
    app.finished = False
    app.play = app.config['settings']['play']
    app.current_video = app.config['settings']['video']
    app.movie = Movie(app.config['settings']['video'],
            desired_size=get_out_shape(app), audio=app.audio)

    app.movie.video_callback(partial(render, app))
    app.set_redis_callback(channel_update)
    app.add_periodic_callback(update_app, 1/60.)
    try:
        app.movie.start()
        app.run()
    except KeyboardInterrupt:
        if app.movie:
            app.movie.pause()
    finally:
        if app.movie:
            app.movie.cleanup()
        app.audio.terminate()
        app.cleanup()


if __name__ == "__main__":
    main(sys.argv[1])
