import os
import PIL

from . import ppm_utils


def pil_image_save(src, det, quality):
    timestamp = os.stat(src).st_ctime
    image = PIL.Image.open(src)
    image = ppm_utils.add_timestamp(image, timestamp)
    image.save(det, format="JPEG", quality=quality)
