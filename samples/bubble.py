# Install requirements:
# brew install portaudio
# pip install pyaudio
import time
import wave
from threading import Thread
from queue import Queue

import cv2
import numpy
import pyaudio

from flipdisc.framework.app import Application


class Audio:

    def __init__(self, aud, filename):
        self.started = False
        self.music = wave.open(filename, "rb")
        self.stream = aud.open(
            format=aud.get_format_from_width(self.music.getsampwidth()),
            channels=self.music.getnchannels(),
            rate=self.music.getframerate(),
            input=False, output=True,
            stream_callback=self.audio_callback,
            start=False)

    def stop(self):
        if self.stream.is_active():
            return True
        if self.started:
            self.stream.stop_stream()
        self.stream.close()
        self.music.close()

    def start(self):
        self.started = True
        self.stream.start_stream()

    def audio_callback(self, in_data, frame_count, time_info, status):
        data = self.music.readframes(frame_count)
        return (data, pyaudio.paContinue)


def stop_audio_stream(app):
    while True:
        audio = app.remove_audio.get()
        if audio.stop():
            # Still running.
            time.sleep(0.5)
            app.remove_audio.put(audio)

        app.remove_audio.task_done()


def create_audio_stream(app, rad):
    if rad <= 15:
        name = "resource/water_normp.wav"
    elif rad <= 25:
        name = "resource/water_lowp.wav"
    else:
        name = "resource/water_highp.wav"
    return Audio(app.aud, name)


def update(app):
    output = numpy.zeros((app.height, app.width), numpy.uint8)

    alive = []
    for i, (center, radius, audio) in enumerate(app.circles):
        if not audio.started:
            audio.start()
        cv2.circle(output, center, radius=radius, color=255, thickness=2)
        radius -= 2
        if radius > 0:
            alive.append((center, radius, audio))
        else:
            app.remove_audio.put(audio)
    app.circles = alive

    if numpy.random.random() < app.config['settings']['intensity']:
        center = numpy.random.randint(15, app.width - 15), numpy.random.randint(15, app.height - 15)
        radius = numpy.random.randint(10, 30)
        aud_stream = create_audio_stream(app, radius)
        app.circles.append((center, radius, aud_stream))

    app.send_output(output)


def main():
    app = Application('bubble', config='sample_config.json')
    app.config['settings'] = {'intensity': 0.2}

    out_cfg = app.config['output_stream']
    app.width = out_cfg['width']
    app.height = out_cfg['height']

    app.aud = pyaudio.PyAudio()
    # Stopping streams blocks for a significant time, so we use a few
    # threads outside main for that.
    app.remove_audio = Queue()
    for _ in range(10):
        audio_stop_worker = Thread(target=stop_audio_stream, args=(app, ))
        audio_stop_worker.daemon = True
        audio_stop_worker.start()

    app.circles = []
    app.add_periodic_callback(update, 1/30.)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        print('audio_stop_worker cleanup..')
        app.remove_audio.join()
        print('terminating pyaudio..')
        app.aud.terminate()
        print('flipdisc cleanup..')
        app.cleanup()


if __name__ == "__main__":
    main()
