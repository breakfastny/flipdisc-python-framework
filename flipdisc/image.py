import cv2
import numpy

from flipdisc import util


def load_image(filename, area_size, binarize=0, padding=0):
    img = cv2.imread(filename)
    if img is None:
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if padding:
        gray = util.pad(gray, padding)

    # Resize if needed.
    resize = max(gray.shape) > min(area_size)
    if resize:
        gray = util.resize(gray, area_size)

    # Binarize.
    if binarize is not None:
        gray[gray <= binarize] = 0
        gray[gray > binarize] = 255

    # Copy image to the center of area.
    area = numpy.zeros(area_size, numpy.uint8)
    util.copy_to_center(area, gray)

    return area
