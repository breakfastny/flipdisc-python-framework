# requirements:
# linux: sudo apt-get install alsa-utils ecasound ffmpeg
# macos: brew install ffmpeg
import cv2
import logging
import numpy
import re
import signal
import subprocess
import sys

from ctypes import cdll

from flipdisc import image
from flipdisc.framework.app import Application
from flipdisc.framework.common import REDIS_KEYS
from flipdisc.binarize import dither_atkinson


clamp = lambda a, b, val: max(a, min(b, val))


def process_frame(app, frame_num, bgr):
    if app.suspended:
        return

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGRA2GRAY)

    out_w, out_h = (app.config['output_stream'][k] for k in ('width', 'height'))
    hdmi_w, hdmi_h = (app.config['hdmi_stream'][k] for k in ('width', 'height'))

    # Crop
    x, y, w, h = (app.config['settings'].get(k, 0) for k in (
        'crop_x', 'crop_y', 'crop_width', 'crop_height'))

    x = clamp(0, hdmi_w-1, x)
    y = clamp(0, hdmi_h-1, y)
    x2 = clamp(0, hdmi_w-1, x+w)
    y2 = clamp(0, hdmi_h-1, y+h)

    if w > 0 and h > 0:
        if y2-y > 0 and x2-x > 0:
            gray = gray[y:y2, x:x2]
        else:
            # blank if one or both sides have length <= 0
            gray = numpy.zeros((out_h, out_w), numpy.uint8)

    # Resize
    resize_mode = app.config['settings'].get('resize_mode', 'stretch')
    resize_factor = app.config['settings'].get('resize_factor', 1)

    resize_func = getattr(image, 'resize_%s' % resize_mode, None)
    if resize_func is None:
        app.log.warning('resize_mode %s not available, using stretch', resize_mode)
        resize_mode = 'stretch'
        resize_func = image.resize_stretch

    if resize_func == getattr(image, 'resize_factor', None):
        contain_h = float(out_h) / gray.shape[0]
        contain_w = float(out_w) / gray.shape[1]
        contain_scale = min(contain_h, contain_w)
        resize_factor = contain_scale * resize_factor
        out = numpy.zeros((out_h, out_w), dtype=numpy.uint8)
        gray = resize_func(gray, out, resize_factor, resize_factor)
    else:
        gray = resize_func(gray, (out_w, out_h), interpolation=cv2.INTER_AREA)

    # Binarize
    bin_method = app.config['settings']['binarize']

    if bin_method == 'dither':
        bin_result = gray.astype(numpy.float)
        dither_atkinson(bin_result)
        bin_result = bin_result.astype(numpy.uint8)
    elif bin_method == 'adaptive':
        gray = cv2.bilateralFilter(gray, 7, 11, 11)
        blocksize = 3
        bin_result = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, blocksize, -1)
    elif bin_method == 'threshold':
        thres = app.config['settings']['threshold']
        gray[gray > thres] = 255
        gray[gray <= thres] = 0
        bin_result = gray
    else:
        bin_result = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    # Invert
    if app.config['settings']['invert']:
        bin_result = numpy.bitwise_not(bin_result)

    app.send_output(bin_result)
    

def _start_audio_process(app):
    """Start forwarding HDMI audio to speakers."""
    if getattr(app, 'audio', None) is not None:
        raise ValueError('audio already started')

    app.log.info('start audio..')

    app.audio = None

    if not app.config['settings']['system']['audio']:
        return

    device_path, device_format = _find_audio_device()
    if device_path is None:
        return

    preexec_fn = None
    if sys.platform.startswith('linux'):
        preexec_fn = _preexec_fn_linux
        args = [
            'ecasound',
            '-D',
            '-r:99',
            '-b:256',
            '-f:s16_le,2,48000',
            '-i', device_path,
            '-o', 'alsahw,0,0'
        ]
    else:
        args = [
            '/usr/local/bin/ffplay',
            '-loglevel', 'panic',
            '-nodisp',
            '-f', device_format,
            '-fflags', 'nobuffer',
            '-flags', 'low_delay',
            '-infbuf',
            '-i', device_path
        ]

    try:
        app.audio = subprocess.Popen(args, preexec_fn=preexec_fn)
    except OSError as e:
        app.log.error('audio failed to start %s', e)


def _stop_audio_process(app):
    """Stop forwarding HDMI audio to speakers."""
    if app.audio:
        app.log.info('term audio...')
        app.audio.terminate()
        app.audio.wait()
        app.audio = None


def _preexec_fn_linux():
    """Ensure subprocess exits when parent exits (on Linux)."""
    PR_SET_PDEATHSIG = 1
    assert cdll['libc.so.6'].prctl(PR_SET_PDEATHSIG, signal.SIGHUP) == 0, 'prctl failed'


def _find_audio_device():
    """Find FFmpeg/ecasound audio input device format and path."""
    if sys.platform.startswith('linux'):
        # All F1 controllers are configured with USB Capture HDMI+ at hw:2
        devices = _list_audio_devices_linux()
        for cardindex, _, carddesc, devindex, _, devdesc in devices:
            if (carddesc, devdesc) == ('USB Capture HDMI+', 'USB Audio'):
                return ('alsahw,%d,%d' % (cardindex, devindex)), 'alsa'
    elif sys.platform == 'darwin':
        # For development machines
        devices = _list_audio_devices_macos()
        for dtype, dindex, ddesc in devices:
            if (dtype, ddesc) == ('audio', 'USB Capture HDMI+'):
                return (':%d' % dindex), 'avfoundation'
    return None, None


def _list_audio_devices_linux():
    """List audio input device on Linux."""

    re_index = r'([0-9]+)'
    re_name = r'([^\[]+)'
    re_desc = r'([^\]]+)'
    re_device = r'^card {0}: {1} \[{2}\], device {0}: {1} \[{2}\]'.format(
            re_index, re_name, re_desc)

    output = ''
    try:
        cmd = ['arecord', '-l']
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except OSError as e:
        output = ''
    except subprocess.CalledProcessError as e:
        output = e.output

    devices = []
    device_type = None
    for line in output.split('\n'):
        # card 2: HDMI [USB Capture HDMI+], device 0: USB Audio [USB Audio]
        # =>
        # (2, 'HDMI', 'USB Capture HDMI+', 0, 'USB Audio', 'USB Audio')
        matches = re.match(re_device, line)
        if matches is None:
            continue
        cindex, cname, cdesc, dindex, dname, ddesc = matches.groups()
        devices.append((int(cindex), cname, cdesc, int(dindex), dname, ddesc))
    return devices


def _list_audio_devices_macos():
    """List FFmpeg audio input devices on macOS."""
    output = ''
    try:
        cmd = ['/usr/local/bin/ffmpeg', '-f', 'avfoundation', '-list_devices', 'true', '-i', '']
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except OSError as e:
        output = ''
    except subprocess.CalledProcessError as e:
        output = e.output

    devices = []
    device_type = None
    for line in output.split('\n'):
        if 'AVFoundation video devices:' in line:
            device_type = 'video'
            continue

        if 'AVFoundation audio devices:' in line:
            device_type = 'audio'
            continue

        if 'AVFoundation input device' in line:
            # [AVFoundation input device @ 0x...] [index] description
            _, _, _, _, _, index, description = line.split(' ', 6)
            index = int(index.strip('[]'))
            devices.append((device_type, index, description))

    return devices


def channel_update(app, channel, update):
    if channel == REDIS_KEYS.APP_CHANNEL + app._app_rkey:
        if 'fd_cmd' in update and not app.suspended:
            if 'suspend' in update['fd_cmd']:
                app.suspended = True
                _stop_audio_process(app)
            elif 'shutdown' in update['fd_cmd']:
                _stop_audio_process(app)
        elif 'system' in update:
            if app.suspended:
                _start_audio_process(app)
                app.suspended = False



def main(cfg_path):
    app = Application("hdmi", cfg_path, setup_input=False, verbose=True)
    app.log = logging.getLogger(__name__)
    app.set_redis_callback(channel_update)
    app.set_input_callback(process_frame, 'hdmi_stream')
    app.audio = None
    app.suspended = False

    if not 'settings' in app.config:
        app.config['settings'] = {}

    if not 'system' in app.config['settings']:
        app.config['settings']['system'] = {}

    if not 'audio' in app.config['settings']['system']:
        app.config['settings']['system']['audio'] = True

    _start_audio_process(app)

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        _stop_audio_process(app)
        app.cleanup()


if __name__ == "__main__":
    import sys
    main(sys.argv[1])
