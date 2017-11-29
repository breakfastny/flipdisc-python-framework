# requirements:
# linux: sudo apt-get install libavdevice-dev libavfilter-dev portaudio19-dev
# macos: brew install ffmpeg portaudio
# python: pip install av pyaudio
import sys
import logging
from functools import partial

import cv2
import numpy
import pyaudio

from flipdisc.framework.common import REDIS_KEYS
from flipdisc.framework.app import Application
from flipdisc.binarize import dither_atkinson
from flipdisc import image

from movie import Movie


def get_out_shape(app):
    width = app.config['output_stream']['width']
    height = app.config['output_stream']['height']
    return (width, height)


def render(app, img, ts, finished=False):
    if finished:
        app.finished = True
        app.log.info('finished video')
        return

    out_shape = get_out_shape(app)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Resize
    resize_mode = app.config['settings'].get('resize_mode')
    if not hasattr(image, 'resize_%s' % resize_mode):
        resize_func = image.resize_stretch
        app.log.warning('resize_mode %s not available, using stretch', resize_mode)
        app.config['settings']['resize_mode'] = 'stretch'
    else:
        resize_func = getattr(image, 'resize_%s' % resize_mode)
    gray = resize_func(gray, out_shape, interpolation=cv2.INTER_AREA)

    if app.config['settings']['binarize'] == 'dither':
        bin_result = gray.astype(numpy.float)
        dither_atkinson(bin_result)
        bin_result = bin_result.astype(numpy.uint8)
    else:
        bin_result = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    trim_cfg = app.config['settings']['trim']
    if any((trim_cfg['top'], trim_cfg['right'],
            trim_cfg['bottom'], trim_cfg['left'])):
        # Trim and then resize it back to the output size.
        height, width = bin_result.shape
        bin_result = bin_result[
                trim_cfg['top']:height - trim_cfg['bottom'],
                trim_cfg['left']:width - trim_cfg['right']]
        bin_result = cv2.resize(bin_result, (width, height), interpolation=cv2.INTER_NEAREST)

    if app.config['settings'].get('invert', False):
        bin_result = ~bin_result

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
    curr_hash = _get_playlist_item_hash(app)
    if app.current_hash != curr_hash or (app.finished and app.config['settings']['loop']):
        # New video file.
        app.log.info('switching from %s to %s', app.current_video, curr_video)
        app.finished = False
        if app.movie:
            app.movie.cleanup()
            app.movie = None
        if curr_video:
            app.movie = Movie(curr_video,
                    desired_size=get_out_shape(app),
                    audio=app.audio if app.config['settings']['system']['audio'] else None)
            app.movie.video_callback(partial(render, app))
            app.movie.start()
            if not app.play:
                app.movie.pause()
        app.current_video = curr_video
        app.current_hash = curr_hash


def channel_update(app, channel, update):
    if channel == REDIS_KEYS.APP_CHANNEL + app._app_rkey:
        if 'fd_cmd' in update and app.movie:
            if 'suspend' in update['fd_cmd']:
                app.suspended = True
                app.movie.pause()
            elif 'shutdown' in update['fd_cmd']:
                app.movie.cleanup()
                app.movie = None
        elif 'play' in update and update['play']:
            if app.suspended and app.movie:
                app.movie.resume()
                app.suspended = False


def _get_playlist_item_hash(app):
    system = app.config['settings'].get('system', {})
    playlist_item = system.get('playlist_item', {})
    instance_id = playlist_item.get('appinstance_id')
    playlist_item_id = playlist_item.get('id')
    playlist_item_started_at = playlist_item.get('started_at')
    video = app.config['settings']['video']
    return instance_id, playlist_item_id, playlist_item_started_at, video


def main(cfg_path):
    app = Application("video", cfg_path, setup_input=False, verbose=True)
    app.log = logging.getLogger(__name__)
    app.audio = pyaudio.PyAudio()
    app.suspended = False
    app.finished = False
    app.play = app.config['settings']['play']
    app.current_video = app.config['settings']['video']
    app.current_hash = _get_playlist_item_hash(app)
    app.movie = Movie(app.config['settings']['video'],
            desired_size=get_out_shape(app),
            audio=app.audio if app.config['settings']['system']['audio'] else None)

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
