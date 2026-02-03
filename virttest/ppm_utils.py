"""
Utility functions to deal with ppm (qemu screendump format) files.

:copyright: Red Hat 2008-2009
"""

from __future__ import division

import glob
import logging
import os
import re
import struct
import time
from functools import reduce

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    Image = None
    logging.getLogger("avocado.app").warning(
        "No python imaging library installed. Screendump and Windows guest BSOD"
        " detection are disabled. In order to enable it, please install "
        "python-imaging or the equivalent for your distro."
    )
# Prevent logs pollution
if Image is not None:
    for _logger_name in logging.root.manager.loggerDict:
        if _logger_name.split(".", 1)[0] == "PIL":
            _pil_logger = logging.getLogger(_logger_name)
            _pil_logger.setLevel(logging.CRITICAL)


try:
    import hashlib
except ImportError:
    import md5

try:
    # Monkey patch importlib.metadata.packages_distributions for Python < 3.10
    # This is needed because some google libraries expect it to exist in stdlib importlib.metadata
    # but it was only added in Python 3.10.
    import sys
    if sys.version_info < (3, 10):
        import importlib.metadata
        import importlib_metadata
        if not hasattr(importlib.metadata, "packages_distributions"):
            importlib.metadata.packages_distributions = importlib_metadata.packages_distributions
except ImportError:
    pass

try:
    import google.generativeai as genai
except ImportError:
    genai = None
    logging.getLogger("avocado.app").warning(
        "google-generativeai library not found. Visual verification with Gemini is disabled."
    )

# Some directory/filename utils, for consistency

LOG = logging.getLogger("avocado." + __name__)


def verify_screen_with_gemini(
    image_path,
    prompt,
    api_key=None,
    model_name="gemini-pro-vision", # Use gemini-pro-vision for images
    save_failed_image=True,
    results_dir=None,
    resize_max_dim=1024,
):
    """
    Verify screen content using Google Gemini API.

    :param image_path: Path to the image file (PPM format expected from QEMU).
    :param prompt: Question to ask about the image.
    :param api_key: Gemini API Key. If None, uses GEMINI_API_KEY env var.
    :param model_name: Model version to use.
    :param save_failed_image: Whether to save the image if validation "fails" (logic depends on prompt).
    :param results_dir: Directory to save failed images.
    :param resize_max_dim: Max dimension to resize image to (maintains aspect ratio).
                           Set to None to disable resizing.
    :return: The text response from Gemini (stripped).
    """
    if not genai:
        raise ImportError(
            "google-generativeai library is required for this feature. "
            "Please install it using 'pip install google-generativeai'."
        )

    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise ValueError("Gemini API Key is required (set GEMINI_API_KEY env var).")

    # Configure Proxy if set in environment
    # requests/urllib3 usually pick up HTTPS_PROXY automatically, but we ensure it's available.
    if "HTTPS_PROXY" not in os.environ and "https_proxy" not in os.environ:
        LOG.warning("No HTTPS_PROXY set. Gemini API access might fail if you are behind a firewall.")

    # Force REST transport to avoid gRPC proxy issues and ensure better compatibility
    genai.configure(api_key=api_key, transport="rest")

    if not Image:
        raise ImportError("Pillow (PIL) is required to process images.")

    try:
        # Open and process image
        with Image.open(image_path) as img:
            # Resize if requested to save bandwidth/quota
            if resize_max_dim:
                img.thumbnail((resize_max_dim, resize_max_dim))

            # Convert to RGB (PPM is RGB, but good safety measure) and save to JPEG in memory
            # JPEG is much smaller than PPM or PNG
            import io

            img_byte_arr = io.BytesIO()
            img.convert("RGB").save(img_byte_arr, format="JPEG", quality=85)
            img_jpeg = Image.open(img_byte_arr)

            # Candidate models to try, in order of preference
            candidate_models = [
                "gemini-flash-latest", # Available per logs
                "gemini-2.0-flash",    # Available per logs
                "gemini-2.5-flash",    # Available per logs
                "gemini-pro-latest",   # Available per logs
                model_name, # The one passed in argument
                "gemini-1.5-flash",
                "gemini-1.5-pro",
                "gemini-pro-vision",
            ]
            # Remove duplicates while preserving order
            candidate_models = list(dict.fromkeys(candidate_models))

            response = None
            last_error = None

            for model_candidate in candidate_models:
                try:
                    LOG.info("Trying Gemini model: %s", model_candidate)
                    model = genai.GenerativeModel(model_candidate)
                    
                    # Retry logic for each model
                    max_retries = 2
                    for attempt in range(max_retries):
                        try:
                            response = model.generate_content(
                                [prompt, img_jpeg],
                                generation_config=genai.types.GenerationConfig(
                                    temperature=0.1
                                )
                            )
                            break # Success inner loop
                        except Exception as e:
                            if "404" in str(e) or "not found" in str(e).lower():
                                # Model not found, break inner retry to try next model
                                raise e 
                            if attempt == max_retries - 1:
                                raise e
                            LOG.warning("Gemini API call failed (attempt %d/%d) for model %s: %s. Retrying...", attempt + 1, max_retries, model_candidate, e)
                            time.sleep(2)
                    
                    if response:
                        break # Success outer loop

                except Exception as e:
                    last_error = e
                    LOG.warning("Model %s failed: %s", model_candidate, e)
                    continue

            if not response:
                LOG.error("All candidate models failed. Listing available models...")
                try:
                    for m in genai.list_models():
                        LOG.info("Available model: %s (methods: %s)", m.name, m.supported_generation_methods)
                except Exception as list_e:
                    LOG.error("Failed to list models: %s", list_e)
                
                raise last_error or Exception("No working Gemini model found")

            result_text = response.text.strip()
            
            # Simple heuristic: if prompt asks for YES/NO and we get NO, save image
            if save_failed_image and results_dir:
                # This logic is loose; caller should decide pass/fail, but we help debug here.
                # If the response starts with "No" (case insensitive), we treat it as suspicious.
                if result_text.lower().startswith("no"):
                    try:
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                        fail_filename = "gemini_fail_%s.jpg" % timestamp
                        fail_path = os.path.join(results_dir, fail_filename)
                        if not os.path.exists(results_dir):
                            os.makedirs(results_dir)
                        # Save the compressed/resized version we actually sent
                        with open(fail_path, "wb") as f:
                            f.write(img_byte_arr.getvalue())
                        LOG.info("Saved failed visual check image to: %s", fail_path)
                    except Exception as e:
                        LOG.error("Failed to save debug image: %s", e)

            return result_text

    except Exception as e:
        LOG.error("Gemini API call failed: %s", e)
        # We re-raise to let the test fail with ERROR status
        raise


def _md5eval(data):
    """
    Returns a md5 hash evaluator. This function is implemented in order to
    encapsulate objects in a way that is compatible with python 2.4 and
    python 2.6 without warnings.

    :param data: Optional input string that will be used to update the object.
    """
    try:
        hsh = hashlib.new("md5")
    except NameError:
        hsh = md5.new()
    if data:
        hsh.update(data)

    return hsh


def find_id_for_screendump(md5sum, data_dir):
    """
    Search dir for a PPM file whose name ends with md5sum.

    :param md5sum: md5 sum string
    :param dir: Directory that holds the PPM files.
    :return: The file's basename without any preceding path, e.g.
             ``20080101_120000_d41d8cd98f00b204e9800998ecf8427e.ppm``
    """
    try:
        files = os.listdir(data_dir)
    except OSError:
        files = []
    for fl in files:
        exp = re.compile(r"(.*_)?" + md5sum + r"\.ppm", re.IGNORECASE)
        if exp.match(fl):
            return fl


def generate_id_for_screendump(md5sum, data_dir):
    """
    Generate a unique filename using the given MD5 sum.

    :return: Only the file basename, without any preceding path. The
             filename consists of the current date and time, the MD5 sum and a
             ``.ppm`` extension, e.g.
             ``20080101_120000_d41d8cd98f00b204e9800998ecf8427e.ppm``.
    """
    filename = time.strftime("%Y%m%d_%H%M%S") + "_" + md5sum + ".ppm"
    return filename


def get_data_dir(steps_filename):
    """
    Return the data dir of the given steps filename.
    """
    filename = os.path.basename(steps_filename)
    return os.path.join(
        os.path.dirname(steps_filename), "..", "steps_data", filename + "_data"
    )


# Functions for working with PPM files


def image_read_from_ppm_file(filename):
    """
    Read a PPM image.

    :return: A 3 element tuple containing the width, height and data of the
            image.
    """
    with open(filename, "rb") as fin:
        fin.readline()
        l2 = fin.readline()
        fin.readline()
        data = fin.read()

    (w, h) = list(map(int, l2.split()))
    return (w, h, data)


def image_write_to_ppm_file(filename, width, height, data):
    """
    Write a PPM image with the given width, height and data.

    :param filename: PPM file path
    :param width: PPM file width (pixels)
    :param height: PPM file height (pixels)
    """
    with open(filename, "wb") as fout:
        fout.write(b"P6\n")
        fout.write(("%d %d\n" % (width, height)).encode())
        fout.write(b"255\n")
        fout.write(data)


def image_crop(width, height, data, x1, y1, dx, dy):
    """
    Crop an image.

    :param width: Original image width
    :param height: Original image height
    :param data: Image data
    :param x1: Desired x coordinate of the cropped region
    :param y1: Desired y coordinate of the cropped region
    :param dx: Desired width of the cropped region
    :param dy: Desired height of the cropped region
    :return: A 3-tuple containing the width, height and data of the
             cropped image.
    """
    if x1 > width - 1:
        x1 = width - 1
    if y1 > height - 1:
        y1 = height - 1
    if dx > width - x1:
        dx = width - x1
    if dy > height - y1:
        dy = height - y1
    newdata = b""
    index = (x1 + y1 * width) * 3
    for _ in range(dy):
        newdata += data[index : (index + dx * 3)]
        index += width * 3
    return (dx, dy, newdata)


def image_md5sum(width, height, data):
    """
    Return the md5sum of an image.

    :param width: PPM file width
    :param height: PPM file height
    :param data: PPM file data
    """
    header = "P6\n%d %d\n255\n" % (width, height)
    hsh = _md5eval(header.encode())
    hsh.update(data)
    return hsh.hexdigest()


def get_region_md5sum(width, height, data, x1, y1, dx, dy, cropped_image_filename=None):
    """
    Return the md5sum of a cropped region.

    :param width: Original image width
    :param height: Original image height
    :param data: Image data
    :param x1: Desired x coord of the cropped region
    :param y1: Desired y coord of the cropped region
    :param dx: Desired width of the cropped region
    :param dy: Desired height of the cropped region
    :param cropped_image_filename: if not None, write the resulting cropped
            image to a file with this name
    """
    (cw, ch, cdata) = image_crop(width, height, data, x1, y1, dx, dy)
    # Write cropped image for debugging
    if cropped_image_filename:
        image_write_to_ppm_file(cropped_image_filename, cw, ch, cdata)
    return image_md5sum(cw, ch, cdata)


def image_verify_ppm_file(filename):
    """
    Verify the validity of a PPM file.

    :param filename: Path of the file being verified.
    :return: True if filename is a valid PPM image file. This function
             reads only the first few bytes of the file so it should be rather
             fast.
    """
    try:
        size = os.path.getsize(filename)
        with open(filename, "rb") as fin:
            assert fin.readline().strip() == b"P6"
            (width, height) = map(int, fin.readline().split())
            assert width > 0 and height > 0
            assert fin.readline().strip() == b"255"
            size_read = fin.tell()
        assert size - size_read == width * height * 3
        return True
    except Exception:
        return False


def image_comparison(width, height, data1, data2):
    """
    Generate a green-red comparison image from two given images.

    :param width: Width of both images
    :param height: Height of both images
    :param data1: Data of first image
    :param data2: Data of second image
    :return: A 3-element tuple containing the width, height and data of the
            generated comparison image.

    :note: Input images must be the same size.
    """
    newdata = ""
    i = 0
    while i < width * height * 3:
        # Compute monochromatic value of current pixel in data1
        pixel1_str = data1[i : i + 3]
        temp = struct.unpack("BBB", pixel1_str)
        value1 = int((temp[0] + temp[1] + temp[2]) / 3)
        # Compute monochromatic value of current pixel in data2
        pixel2_str = data2[i : i + 3]
        temp = struct.unpack("BBB", pixel2_str)
        value2 = int((temp[0] + temp[1] + temp[2]) / 3)
        # Compute average of the two values
        value = int((value1 + value2) / 2)
        # Scale value to the upper half of the range [0, 255]
        value = 128 + value // 2
        # Compare pixels
        if pixel1_str == pixel2_str:
            # Equal -- give the pixel a greenish hue
            newpixel = [0, value, 0]
        else:
            # Not equal -- give the pixel a reddish hue
            newpixel = [value, 0, 0]
        newdata += struct.pack("BBB", newpixel[0], newpixel[1], newpixel[2])
        i += 3
    return (width, height, newdata)


def image_fuzzy_compare(width, height, data1, data2):
    """
    Return the degree of equality of two given images.

    :param width: Width of both images
    :param height: Height of both images
    :param data1: Data of first image
    :param data2: Data of second image
    :return: Ratio equal_pixel_count / total_pixel_count.

    :note: Input images must be the same size.
    """
    equal = 0.0
    different = 0.0
    i = 0
    while i < width * height * 3:
        pixel1_str = data1[i : i + 3]
        pixel2_str = data2[i : i + 3]
        # Compare pixels
        if pixel1_str == pixel2_str:
            equal += 1.0
        else:
            different += 1.0
        i += 3
    return equal / (equal + different)


def image_average_hash(image, img_wd=8, img_ht=8):
    """
    Resize and convert the image, then get image data as sequence object,
    calculate the average hash
    :param image: an image path or an opened image object
    """
    if not isinstance(image, Image.Image):
        image = Image.open(image)
    image = image.resize((img_wd, img_ht), Image.ANTIALIAS).convert("L")
    avg = reduce(lambda x, y: x + y, image.getdata()) / (img_wd * img_ht)

    def _hta(i):
        if i < avg:
            return 0
        else:
            return 1

    return reduce(
        lambda x, y_z: x | (y_z[1] << y_z[0]), enumerate(map(_hta, image.getdata())), 0
    )


def cal_hamming_distance(h1, h2):
    """
    Calculate the hamming distance
    """
    h_distance, distance = 0, h1 ^ h2
    while distance:
        h_distance += 1
        distance &= distance - 1
    return h_distance


def img_ham_distance(base_img, comp_img):
    """
    Calculate two images hamming distance
    """
    base_img_ahash = image_average_hash(base_img)
    comp_img_ahash = image_average_hash(comp_img)
    return cal_hamming_distance(comp_img_ahash, base_img_ahash)


def img_similar(base_img, comp_img, threshold=10):
    """
    check whether two images are similar by hamming distance
    """
    try:
        hamming_distance = img_ham_distance(base_img, comp_img)
    except IOError:
        return False

    if hamming_distance < threshold:
        return True
    else:
        return False


def have_similar_img(base_img, comp_img_path, threshold=10):
    """
    Check whether comp_img_path have a image looks like base_img.
    """
    support_img_format = ["jpg", "jpeg", "gif", "png", "pmp"]
    comp_images = []
    if os.path.isdir(comp_img_path):
        for ext in support_img_format:
            comp_images.extend(
                [
                    os.path.join(comp_img_path, x)
                    for x in glob.glob1(comp_img_path, "*.%s" % ext)
                ]
            )
    else:
        comp_images.append(comp_img_path)

    for img in comp_images:
        if img_similar(base_img, img, threshold):
            return True
    return False


def image_crop_save(image, new_image, box=None):
    """
    Crop an image and save it to a new image.

    :param image: Full path of the original image
    :param new_image: Full path of the cropped image
    :param box: A 4-tuple defining the left, upper, right, and lower pixel coordinate.
    :return: True if crop and save image succeed
    """
    img = Image.open(image)
    if not box:
        x, y = img.size
        box = (x / 4, y / 4, x * 3 / 4, y * 3 / 4)
    try:
        img.crop(box).save(new_image)
    except (KeyError, SystemError) as e:
        LOG.error("Fail to crop image: %s", e)
        return False
    return True


def image_histogram_compare(image_a, image_b, size=(0, 0)):
    """
    Compare the histogram of two images and return similar degree.

    :param image_a: Full path of the first image
    :param image_b: Full path of the second image
    :param size: Convert image to size(width, height), and if size=(0, 0), the function will convert the big size image align with the small one.
    """
    img_a = Image.open(image_a)
    img_b = Image.open(image_b)
    if not any(size):
        size = tuple(map(max, img_a.size, img_b.size))
    img_a_h = img_a.resize(size).convert("RGB").histogram()
    img_b_h = img_b.resize(size).convert("RGB").histogram()
    s = 0
    for i, j in list(zip(img_a_h, img_b_h)):
        if i == j:
            s += 1
        else:
            s += 1 - float(abs(i - j)) / max(i, j)
    return s / len(img_a_h)


def add_timestamp(image, timestamp, margin=2):
    """
    Return an image object with timestamp bar added at the bottom.

    param image: pillow image object
    param timestamp: timestamp in seconds since the Epoch
    param margin: timestamp margin, default is 2
    """
    width, height = image.size
    font = ImageFont.load_default()
    watermark = time.strftime("%c", time.localtime(timestamp))
    # bar height = text height + top margin + bottom margin
    if hasattr(font, "getbbox"):
        bar_height = font.getbbox(watermark)[3] + 2 * margin
    else:
        bar_height = font.getsize(watermark)[1] + 2 * margin

    # place bar at the bottom
    new_image = ImageOps.expand(image, border=(0, 0, 0, bar_height), fill="lightgrey")
    draw = ImageDraw.Draw(new_image)
    # place timestamp at the left side of the bar
    x, y = margin, height + margin
    draw.text((x, y), watermark, font=font, fill="black")
    return new_image


def image_size(image):
    """
    Return image's size as a tuple (width, height).

    :param image: image file.
    """

    img = Image.open(image)
    return img.size
