import cv2
import numpy


def image_to_particles(emitter, bin_image):
    """
    Add every point from bin_image != 0 as a particle.

    * emitter should be an instance of flipdisc.particle.Emitter
    * bin_image should be a numpy 2d array
    """
    emitter.clear()
    for coord in numpy.argwhere(bin_image != 0):
        emitter.add_particle(tuple(coord))


def flip(arr, mirror, upsidedown):
    """Flips a numpy array and return it."""
    if mirror:
        arr = numpy.fliplr(arr)
    if upsidedown:
        arr = numpy.flipud(arr)
    return arr


def pad(image, size, value=0):
    """Pad and return image with border size and value specified."""
    return numpy.pad(image, size, 'constant', constant_values=value)


def resize(image, target_size):
    """
    Resize image to the target size while keeping the aspect ratio.
    A new image of size <= target_size is returned.

    * image is assumed to be a numpy 2d array with a single channel
    * target_size is assumed to be a tuple of integers (height, width)
    """
    height, width = target_size

    im_height, im_width = image.shape
    ratio_a = im_width / float(im_height)
    ratio_b = im_height / float(im_width)

    if width * ratio_b <= height:
        final_size = (width, int(width * ratio_b))
    else:
        final_size = (int(height * ratio_a), height)

    if min(target_size) > max(image.shape):
        interpolation = cv2.INTER_LINEAR
    else:
        interpolation = cv2.INTER_AREA

    return cv2.resize(image, final_size, interpolation=interpolation)


def copy_to_center(dest, img):
    """
    Copy img to the center of dest.

    * dest must be at least as big as img
    * img and dest should both be numpy arrays
    """
    dest_height, dest_width = dest.shape
    src_height, src_width = img.shape
    if src_height > dest_height or src_width > dest_width:
        raise Exception('img %s is larger than dest %s' % (img.shape, dest.shape))

    d_half = dest_height / 2, dest_width / 2
    (half_h, half_exh), (half_w, half_exw) = divmod(src_height, 2), divmod(src_width, 2)
    dest[d_half[0] - half_h:d_half[0] + half_h + half_exh,
         d_half[1] - half_w:d_half[1] + half_w + half_exw] = img
