# requirements: pip install av pyaudio
import time
import math
import logging
from multiprocessing import Process, Queue, Event
from Queue import Empty as QueueEmpty

import av
import pyaudio

from flipdisc.framework.app import ioloop as app_ioloop

__all__ = ['Movie']


class Movie(object):

    def __init__(self, filepath, desired_size, audio, start_queueing=True, ioloop=None):
        self._log = logging.getLogger(__name__)

        self.video_info = None
        self.audio_info = None

        self._audio = audio
        self._audio_player = None

        width, height = desired_size
        self._vwidth = int(math.ceil(width / 16.) * 16)
        self._vheight = int(math.ceil(height / 16.) * 16)
        self._video_queue = Queue(maxsize=1024)
        self._audio_queue = Queue()
        self._first_video_ts = None

        self._container = av.open(str(filepath))

        self._video_stream = None
        self._audio_stream = None
        self._proc = None
        self._stop = False
        self._keep_queueing = Event()
        self._keep_queueing.set()
        self._finished = Event()
        self._last_at = 0
        self._last_vts = 0
        self._last_vts_remaining = 0
        self._ioloop = ioloop or app_ioloop.IOLoop.current()

        self._init_streams()

        if start_queueing:
            self.start_queueing()

    def start_queueing(self):
        if self._proc is not None:
            return

        if self.audio_info:
            framerate = self.audio_info['rate']
            self._audio_player = AudioStream(self._finished,
                    self._audio, self._audio_queue, framerate)

        args = (self._keep_queueing, self._finished, self._container.name,
                self._video_queue, self._audio_queue)
        if self._video_stream:
            args += (self._video_stream.index, )
        if self._audio_stream:
            args += (self._audio_stream.index, )
        self._proc = Process(target=self._enqueue, args=args)
        self._proc.daemon = True
        self._proc.start()

    def start(self):
        if self._audio_player:
            self._audio_player.play()
        self._log.info('start')

    def pause(self):
        if self._stop:
            return
        self._log.info('stopping..')

        if self._audio_player:
            self._audio_player.pause()

        self._keep_queueing.clear()
        if self._last_vts:
            self._last_vts_remaining = self._last_vts - time.time()
        self._first_video_ts = None
        self._stop = True

        self._log.info('stopped')

    def resume(self):
        if not self._stop:
            return
        self._log.info('resume')

        self._keep_queueing.set()

        if self._audio_player:
            self._audio_player.play()

        self._stop = False

    def cleanup(self):
        self._stop = True
        if self._audio_player:
            self._audio_player.kill()
            self._audio_player = None

        if self._proc is not None:
            self._log.info('closing enqueuer process..')
            self._proc.terminate()
            self._proc.join()
            self._proc = None
            self._log.info('closed')

    def video_callback(self, cb):
        if self._stop:
            self._ioloop.call_later(0.01, self.video_callback, cb)
            return

        try:
            past_img, past_play_at, next_play_at = self._video_queue.get_nowait()
        except QueueEmpty:
            if self._finished.is_set():
                cb(None, None, finished=True)
            else:
                self._ioloop.call_later(0.005, self.video_callback, cb)
            return

        if past_img is None or self._first_video_ts is None:
            # Video just started,
            # or a new loop just started (past_img is None),
            # or the video was resumed (self._first_video_ts is None).
            if past_img is None:
                self._first_video_ts = time.time()
            else:
                self._first_video_ts = time.time() - self._last_at + self._last_vts_remaining
            self._last_at = 0
            self._last_vts = 0
            self._last_vts_remaining = 0

        past_play_at = past_play_at or 0
        if past_img is not None:
            # Schedule the callback to execute at the presentation time for
            # this frame.
            present_at = self._first_video_ts + past_play_at
            self._last_at = past_play_at
            self._last_vts = present_at
            self._ioloop.call_at(present_at, cb, past_img, present_at)

        # Schedule this function to execute again at the known presentation
        # time for the next frame.
        next_at = self._first_video_ts + next_play_at
        self._ioloop.call_at(next_at, self.video_callback, cb)

    def _enqueue(self, run, finished, filepath, vid_q, aud_q, *stindex):
        aud_resampler = av.AudioResampler(
            format=av.AudioFormat('s16p').packed,   # WAV PCM signed 16bit planar
            layout='stereo',
        )

        def decode():
            print 'started decoding and queueing'
            container = av.open(filepath)
            streams = [container.streams[indx] for indx in stindex]
            prev_video_frame = None
            prev_video_ts = None
            for packet in container.demux(streams):
                run.wait()
                for frame in packet.decode():
                    play_at = float(frame.time_base * frame.pts) if frame.pts else None
                    if isinstance(frame, av.AudioFrame):
                        frame_r = aud_resampler.resample(frame)
                        raw_audio = frame_r.planes[0].to_bytes()
                        aud_q.put(raw_audio)
                    elif isinstance(frame, av.VideoFrame):
                        if frame.width <= 320 and frame.height <= 240:
                            # Use size as is.
                            frame_bgr = frame.to_nd_array(format='bgr24')
                        else:
                            # Scale down to keep things fast.
                            frame_bgr = frame.to_nd_array(
                                    width=self._vwidth, height=self._vheight,
                                    format='bgr24')
                        vid_q.put((prev_video_frame, prev_video_ts, play_at or 0))
                        prev_video_frame = frame_bgr.copy()
                        prev_video_ts = play_at or 0
                    else:
                        print 'unknown frame', frame
            print 'finished decoding and queueing'

        decode()
        finished.set()

    def _init_streams(self):
        for stream in self._container.streams:
            if stream.type == 'video':
                self.__init_video(stream)
            elif stream.type == 'audio':
                self.__init_audio(stream)

    def __init_video(self, stream):
        if self.video_info:
            return

        self._video_stream = stream
        self.video_info = {
            'fps': float(stream.average_rate),
            'frame_count': stream.frames,
        }

    def __init_audio(self, stream):
        if self.audio_info:
            return

        self._audio_stream = stream
        if not stream.frame_size:
            # Decode first audio frame to find out the number of samples.
            first_packet = next(self._container.demux(stream))
            first_frame = first_packet.decode()[0]
            sample_size = first_frame.samples
            self._container.seek(-1)
        else:
            sample_size = stream.frame_size

        self.audio_info = {
            'channels': stream.channels,
            'rate': stream.rate,
            'format': stream.format,
            'sample_size': sample_size,
        }


class AudioStream(object):

    def __init__(self, finished_event, aud, audio_queue, framerate):
        self._log = logging.getLogger(__name__)
        self.playing = False
        self._finished = finished_event
        self._audio_queue = audio_queue
        self._audio_queue_extra = Queue()
        self._stream = None
        try:
            self._stream = aud.open(
                format=aud.get_format_from_width(2),
                channels=2,
                rate=framerate,
                input=False, output=True,
                stream_callback=self._audio_callback,
                start=False)
        except IOError:
            self._log.exception('failed to open audio')

    def play(self):
        if self._stream is None or self.playing:
            return
        self.playing = True
        self._stream.start_stream()

    def pause(self):
        if self._stream is None or not self.playing:
            return
        self.playing = False
        self._stream.stop_stream()

    def kill(self):
        if self._stream is None:
            return
        self.pause()
        self._stream.close()

    def _audio_callback(self, in_data, frame_count, time_info, status):
        size = frame_count * 2 * 2  # 2 bytes each, 2 channels
        raw = ''

        while True:
            # Clear extra queue, if there's anything.
            try:
                raw = raw + self._audio_queue_extra.get_nowait()
            except QueueEmpty:
                break

        while len(raw) < size:
            # Use regular queue.
            try:
                raw = raw + self._audio_queue.get_nowait()
            except QueueEmpty:
                break

        if len(raw) > size:
            self._audio_queue_extra.put(raw[size:])
            raw = raw[:size]
        elif len(raw) < size:
            if self._finished.is_set():
                return ('\x00' * size, pyaudio.paComplete)
            self._log.error('Audio underflow: wanted %d, got %d', size, len(raw))

        data = raw + ('\x00' * (size - len(raw)))
        return (data, pyaudio.paContinue)
