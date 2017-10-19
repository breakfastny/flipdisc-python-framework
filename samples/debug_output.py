import cv2
import numpy

from flipdisc.framework import OUTPUT_STREAM
from flipdisc.framework.app import Application


pixel_pad = numpy.zeros((5, 5), numpy.uint8)
pixel_pad[2, 2] = 1
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

def process_frame(app, subtopic, frame_num, bin_image):
    scale = app.config['settings']['scale']
    if scale > 1:
        kronecker = app.config['settings']['kron']
        if kronecker:
            bin_image = numpy.kron(bin_image, pixel_pad)
            bin_image = cv2.dilate(bin_image, kernel)
        else:
            bin_image = cv2.resize(bin_image, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)

    cv2.imshow('out', bin_image)
    cv2.waitKey(10)


def main():
    app = Application("preview", 'sample_config.json',
            setup_input=False, setup_output=False, verbose=True)
    app.config['settings'] = {'scale': 2, 'kron': False}
    app.setup_input('output_stream', OUTPUT_STREAM, bind=False)
    app.set_input_callback(process_frame, 'output_stream')
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.cleanup()


if __name__ == "__main__":
    main()
