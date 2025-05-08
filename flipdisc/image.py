import cv2
import numpy

from flipdisc import util

__all__ = [
    "INTER_NEAREST",
    "INTER_LINEAR",
    "INTER_AREA",
    "INTER_CUBIC",
    "INTER_LANCZOS4",
    "resize_stretch",
    "resize_cover",
    "resize_contain",
    "resize_factor",
    "load_image",
]


# A nearest-neighbor interpolation.
INTER_NEAREST = cv2.INTER_NEAREST

# A bilinear interpolation.
INTER_LINEAR = cv2.INTER_LINEAR

# Resampling using pixel area relation.
# It may be a preferred method for image decimation,
# as it gives moire'-free results. But when the image is zoomed,
# it is similar to the INTER_NEAREST method.
INTER_AREA = cv2.INTER_AREA

# A bicubic interpolation over 4x4 pixel neighborhood.
INTER_CUBIC = cv2.INTER_CUBIC

# A Lanczos interpolation over 8x8 pixel neighborhood.
INTER_LANCZOS4 = cv2.INTER_LANCZOS4


def resize_stretch(im, out_size, interpolation=INTER_NEAREST):
    """
    * im: numpy array
    * out_size: tuple of integers (width, height)

    Return the stretched image im that fills out_size.
    """
    return cv2.resize(im, out_size, interpolation=interpolation)


def resize_contain(im, out_size, bgcolor=0, interpolation=INTER_NEAREST):
    """
    * im: numpy array
    * out_size: tuple of integers (width, height)
    * bgcolor: integer >= 0, used to fill the background
    * interpolation: interpolation method to use

    Return a scaled image im to the largest size that fits out_size.
    """
    im_height, im_width = im.shape[:2]
    im_ratio = im_width / float(im_height)
    out_ratio = out_size[0] / float(out_size[1])
    if im_ratio <= out_ratio:
        out_width = int(out_size[1] * im_ratio)
        out_height = out_size[1]
    else:
        out_width = out_size[0]
        out_height = int(out_size[0] / im_ratio)

    if 0 in (out_width, out_height):
        return numpy.zeros((out_size[1], out_size[0]), im.dtype)

    out = cv2.resize(im, (out_width, out_height), interpolation=interpolation)
    # If the output is too small, center it based on the specified size.
    if out.shape[1] < out_size[0]:
        extra_width = out_size[0] - out.shape[1]
        one_more = extra_width % 2
        out1 = numpy.zeros((out.shape[0], out_size[0]) + (out.shape[2:]), out.dtype)
        if bgcolor:
            out1.fill(bgcolor)
        out1[:, extra_width / 2 : -(extra_width / 2 + one_more)] = out
        out = out1
    if out.shape[0] < out_size[1]:
        extra_height = out_size[1] - out.shape[0]
        one_more = extra_height % 2
        out1 = numpy.zeros((out_size[1], out.shape[1]) + (out.shape[2:]), out.dtype)
        if bgcolor:
            out1.fill(bgcolor)
        out1[extra_height / 2 : -(extra_height / 2 + one_more), :] = out
        out = out1

    return out


def resize_factor(im, out, fx, fy, interpolation=None):
    """
    * im: numpy array
    * out: numpy array
    * fx: float x-axis scale factor
    * fy: float y-axis scale factor
    * interpolation: interpolation method to use

    Resize image and paste the result over the center of out; edges are
    cropped if necessary.
    """
    assert fx > 0, "fx must be positive"
    assert fy > 0, "fy must be positive"

    if interpolation is None:
        if fx < 1 or fy < 1:
            interpolation = cv2.INTER_AREA
        else:
            interpolation = cv2.INTER_NEAREST

    scaled_size = (int(fy * im.shape[1]), int(fx * im.shape[0]))
    if 0 in scaled_size:
        return out

    scaled = cv2.resize(im, scaled_size, interpolation=interpolation)
    ih, iw = scaled.shape[:2]
    oh, ow = out.shape[:2]

    x = y = ix = iy = 0
    x2, y2 = x + ow, y + oh
    ix2, iy2 = ix + iw, iy + ih

    if iw < ow:
        x = (ow - iw) / 2
        x2 = x + iw
    elif iw > ow:
        ix = (iw - ow) / 2
        ix2 = ix + ow

    if ih < oh:
        y = (oh - ih) / 2
        y2 = y + ih
    elif ih > oh:
        iy = (ih - oh) / 2
        iy2 = iy + oh

    out[y:y2, x:x2] = scaled[iy:iy2, ix:ix2]
    return out


def resize_cover(im, out_size, interpolation=INTER_NEAREST):
    """
    * im: numpy array
    * out_size: tuple of integers (width, height)
    * interpolation: interpolation method to use

    Return an image such that im covers out_size; edges are cropped if necessary.
    """
    im_height, im_width = im.shape[:2]
    im_ratio = im_width / float(im_height)
    out_ratio = out_size[0] / float(out_size[1])
    if im_ratio <= out_ratio:
        out_width = out_size[0]
        out_height = int(out_size[0] / im_ratio)
    else:
        out_width = int(out_size[1] * im_ratio)
        out_height = out_size[1]

    out = cv2.resize(im, (out_width, out_height), interpolation=interpolation)
    # If the output is too big, crop edges to match the specified size.
    if out.shape[1] > out_size[0]:
        extra_width = out.shape[1] - out_size[0]
        one_more = extra_width % 2
        out = out[:, extra_width / 2 : -(extra_width / 2 + one_more)]
    if out.shape[0] > out_size[1]:
        extra_height = out.shape[0] - out_size[1]
        one_more = extra_height % 2
        out = out[extra_height / 2 : -(extra_height / 2 + one_more), :]

    return out


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
        if binarize >= 0:
            gray[gray <= binarize] = 0
            gray[gray > binarize] = 255
        else:
            # Use otsu.
            gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    # Copy image to the center of area.
    area = numpy.zeros(area_size, numpy.uint8)
    util.copy_to_center(area, gray)

    return area
