"""
Video Maker transforms screenshots taken during a test into a HTML 5
compatible video, so that one can watch the screen activity of the
whole test from inside your own browser.

This relies on generally available multimedia libraries, frameworks
and tools.
"""


import os
import time
import glob
import logging
import re


__all__ = ['get_video_maker_klass', 'video_maker']

#
# Check what kind of video libraries tools we have available
#
# Gobject introspection bindings are our first choice
GI_GSTREAMER_INSTALLED = False
try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    GI_GSTREAMER_INSTALLED = True
except (ImportError, ValueError):
    pass

#
# Gstreamer python bindings are our fallback choice
GST_PYTHON_INSTALLED = False
if not GI_GSTREAMER_INSTALLED:
    try:
        import gst
        GST_PYTHON_INSTALLED = True
    except ImportError:
        pass

#
# PIL is also required to normalize images
#
try:
    import PIL.Image
    PIL_INSTALLED = True
except ImportError:
    PIL_INSTALLED = False


#
# We only do video
#
CONTAINER_PREFERENCE = ['ogg', 'webm']
ENCODER_PREFERENCE = ['theora', 'vp8']

LOG = logging.getLogger('avocado.' + __name__)


class EncodingError(Exception):

    def __init__(self, err, debug):
        self.err = err
        self.debug = debug

    def __str__(self):
        return "Gstreamer Error: %s\nDebug Message: %s" % (self.err, self.debug)


class GiEncoder(object):

    """
    Encodes a video from Virtual Machine screenshots (jpg files).

    This is the gobject-introspection version.

    First, a directory with screenshots is inspected, and the screenshot sizes,
    normalized. After that, the video is encoded, using a gstreamer pipeline
    that goes like (using gstreamer terminology):

    multifilesrc -> jpegdec -> vp8enc -> webmmux -> filesink
    """

    def __init__(self, verbose=False):
        if not GI_GSTREAMER_INSTALLED:
            raise ValueError('pygobject library was not found')
        if not PIL_INSTALLED:
            raise ValueError('python-imaging library was not found')
        self.verbose = verbose
        Gst.init(None)

    def convert_to_jpg(self, input_dir):
        """
        Convert .ppm files inside [input_dir] to .jpg files.

        :param input_dir: Directory to inspect.
        """
        image_files = glob.glob(os.path.join(input_dir, '*.ppm'))
        for ppm_file in image_files:
            ppm_file_basename = os.path.basename(ppm_file)
            jpg_file_basename = ppm_file_basename[:-4] + '.jpg'
            jpg_file = os.path.join(input_dir, jpg_file_basename)
            i = PIL.Image.open(ppm_file)
            i.save(jpg_file, format="JPEG", quality=95)
            os.remove(ppm_file)

    def get_most_common_image_size(self, input_dir):
        """
        Find the most common image size on a directory containing .jpg files.

        :param input_dir: Directory to inspect.
        """
        image_sizes = [PIL.Image.open(path).size for path in
                       glob.glob(os.path.join(input_dir, '*.jpg'))]
        return max(set(image_sizes), key=image_sizes.count)

    def normalize_images(self, input_dir):
        """
        Normalize images of different sizes so we can encode a video from them.

        :param input_dir: Directory with images to be normalized.
        """
        image_size = self.get_most_common_image_size(input_dir)
        if not isinstance(image_size, (tuple, list)):
            image_size = (800, 600)
        else:
            if image_size[0] < 640:
                image_size[0] = 640
            if image_size[1] < 480:     # is list pylint: disable=E1136
                image_size[1] = 480

        if self.verbose:
            LOG.debug('Normalizing image files to size: %s' % (image_size,))
        image_files = glob.glob(os.path.join(input_dir, '*.jpg'))
        for f in image_files:
            i = PIL.Image.open(f)
            if i.size != image_size:
                i.resize(image_size).save(f)

    def has_element(self, kind):
        """
        Returns True if a gstreamer element is available
        """
        return Gst.ElementFactory.find(kind)

    def get_container_name(self):
        """
        Gets the video container available that is the best based on preference
        """
        return 'webmmux'

    def get_encoder_name(self):
        """
        Gets the video encoder available that is the best based on preference
        """
        return 'vp8enc'

    def get_element(self, name):
        """
        Makes and returns and element from the gst factory interface
        """
        return Gst.ElementFactory.make(name, name)

    def encode(self, input_dir, output_file):
        """
        Process the input files and output the video file.

        The encoding part of it is equivalent to

        gst-launch multifilesrc location=[input_dir]/%04d.jpg index=1
        caps='image/jpeg, framerate=(fraction)4/1' !
        jpegdec ! vp8enc ! webmmux ! filesink location=[output_file]

        :param input_dir: Directory with images to be encoded into a video.
        :param output_file: Path to the output video file.
        """
        self.convert_to_jpg(input_dir)
        self.normalize_images(input_dir)

        file_list = glob.glob(os.path.join(input_dir, '*.jpg'))

        no_files = len(file_list)
        if no_files == 0:
            if self.verbose:
                LOG.debug("Number of files to encode as video is zero")
            return

        index_list = [int(path[-8:-4]) for path in file_list]
        index_list.sort()

        if self.verbose:
            LOG.debug('Number of files to encode as video: %s' % no_files)

        # Define the gstreamer pipeline
        pipeline = Gst.Pipeline()

        # Message bus - it allows us to control the end of the encoding process
        # asynchronously
        message_bus = pipeline.get_bus()
        message_bus.add_signal_watch()

        # Defining source properties (multifilesrc, jpegs and framerate)
        source = Gst.ElementFactory.make("multifilesrc", "multifilesrc")
        source_location = os.path.join(input_dir, "%04d.jpg")
        source.set_property('location', source_location)
        # The index property won't work in Fedora 21 Alpha, see bug:
        # https://bugzilla.gnome.org/show_bug.cgi?id=739472
        source.set_property('start-index', index_list[0])
        source_caps = Gst.caps_from_string('image/jpeg, framerate=(fraction)4/1')
        source.set_property('caps', source_caps)

        # Decoder element (jpeg format decoder)
        decoder = self.get_element("jpegdec")

        # Decoder element (vp8 format encoder)
        encoder = self.get_element("vp8enc")

        # Container (WebM container)
        container = self.get_element("webmmux")

        # Defining output properties
        output = self.get_element("filesink")
        output.set_property('location', output_file)

        # Adding all elements to the pipeline
        pipeline.add(source)
        pipeline.add(decoder)
        pipeline.add(encoder)
        pipeline.add(container)
        pipeline.add(output)

        # Linking all elements
        source.link(decoder)
        decoder.link(encoder)
        encoder.link(container)
        container.link(output)

        # Set pipeline to Gst.State.PLAYING
        pipeline.set_state(Gst.State.PLAYING)

        # Wait until the stream stops
        err = None
        debug = None
        while True:
            msg = message_bus.timed_pop(Gst.CLOCK_TIME_NONE)
            t = msg.type
            if t == Gst.MessageType.EOS:
                pipeline.set_state(Gst.State.NULL)
                if self.verbose:
                    LOG.debug("Video %s encoded successfully" % output_file)
                break
            elif t == Gst.MessageType.ERROR:
                err, debug = msg.parse_error()
                pipeline.set_state(Gst.State.NULL)
                break

        if err is not None:
            raise EncodingError(err, debug)


class GstEncoder(object):

    """
    Encodes a video from Virtual Machine screenshots (jpg files).

    This is the python-gstreamer version.

    First, a directory with screenshots is inspected, and the screenshot sizes,
    normalized. After that, the video is encoded, using a gstreamer pipeline
    that goes like (using gstreamer terminology):

    multifilesrc -> jpegdec -> vp8enc -> webmmux -> filesink
    """

    CONTAINER_MAPPING = {'ogg': 'oggmux',
                         'webm': 'webmmux'}

    ENCODER_MAPPING = {'theora': 'theoraenc',
                       'vp8': 'vp8enc'}

    CONTAINER_ENCODER_MAPPING = {'ogg': 'theora',
                                 'webm': 'vp8'}

    def __init__(self, verbose=False):
        if not GST_PYTHON_INSTALLED:
            raise ValueError('gstreamer-python library was not found')
        if not PIL_INSTALLED:
            raise ValueError('python-imaging library was not found')

        self.verbose = verbose

    def get_most_common_image_size(self, input_dir):
        """
        Find the most common image size
        """
        image_sizes = {}
        image_files = glob.glob(os.path.join(input_dir, '*.jpg'))
        for f in image_files:
            i = PIL.Image.open(f)
            if i.size not in image_sizes:
                image_sizes[i.size] = 1
            else:
                image_sizes[i.size] += 1

        most_common_size_counter = 0
        most_common_size = None
        for image_size, image_counter in list(image_sizes.items()):
            if image_counter > most_common_size_counter:
                most_common_size_counter = image_counter
                most_common_size = image_size
        return most_common_size

    def normalize_images(self, input_dir):
        """
        GStreamer requires all images to be the same size, so we do it here
        """
        image_size = self.get_most_common_image_size(input_dir)
        if image_size is None:
            image_size = (800, 600)

        if self.verbose:
            LOG.debug('Normalizing image files to size: %s', image_size)
        image_files = glob.glob(os.path.join(input_dir, '*.jpg'))
        for f in image_files:
            i = PIL.Image.open(f)
            if i.size != image_size:
                i.resize(image_size).save(f)

    def has_element(self, kind):
        """
        Returns True if a gstreamer element is available
        """
        return gst.element_factory_find(kind) is not None

    def get_container_name(self):
        """
        Gets the video container available that is the best based on preference
        """
        for c in CONTAINER_PREFERENCE:
            element_kind = self.CONTAINER_MAPPING.get(c, c)
            if self.has_element(element_kind):
                return element_kind

        raise ValueError('No suitable container format was found')

    def get_encoder_name(self):
        """
        Gets the video encoder available that is the best based on preference
        """
        for c in ENCODER_PREFERENCE:
            element_kind = self.ENCODER_MAPPING.get(c, c)
            if self.has_element(element_kind):
                return element_kind

        raise ValueError('No suitable encoder format was found')

    def get_element(self, name):
        """
        Makes and returns and element from the gst factory interface
        """
        if self.verbose:
            LOG.debug('GStreamer element requested: %s', name)
        return gst.element_factory_make(name, name)

    def encode(self, input_dir, output_file):
        """
        Process the input files and output the video file
        """
        self.normalize_images(input_dir)
        file_list = glob.glob(os.path.join(input_dir, '*.jpg'))
        no_files = len(file_list)
        if no_files == 0:
            if self.verbose:
                LOG.debug("Number of files to encode as video is zero")
            return
        index_list = []
        for ifile in file_list:
            index_list.append(int(re.findall(r"/+.*/(\d{4})\.jpg", ifile)[0]))
            index_list.sort()
        if self.verbose:
            LOG.debug('Number of files to encode as video: %s', no_files)

        pipeline = gst.Pipeline("pipeline")

        source = self.get_element("multifilesrc")
        source_location = os.path.join(input_dir, "%04d.jpg")
        if self.verbose:
            LOG.debug("Source location: %s", source_location)
        source.set_property('location', source_location)
        source.set_property('index', index_list[0])
        source_caps = gst.Caps()
        source_caps.append('image/jpeg,framerate=(fraction)4/1')
        source.set_property('caps', source_caps)

        decoder = self.get_element("jpegdec")

        # Attempt to auto detect the chosen encoder/mux based on output_file
        encoder = None
        container = None

        for container_name in self.CONTAINER_ENCODER_MAPPING:
            if output_file.endswith('.%s' % container_name):

                enc_name = self.CONTAINER_ENCODER_MAPPING[container_name]
                enc_name_gst = self.ENCODER_MAPPING[enc_name]
                encoder = self.get_element(enc_name_gst)

                cont_name_gst = self.CONTAINER_MAPPING[container_name]
                container = self.get_element(cont_name_gst)

        # If auto detection fails, choose from the list of preferred codec/mux
        if encoder is None:
            encoder = self.get_element(self.get_encoder_name())
        if container is None:
            container = self.get_element(self.get_container_name())

        output = self.get_element("filesink")
        output.set_property('location', output_file)

        pipeline.add_many(source, decoder, encoder, container, output)
        gst.element_link_many(source, decoder, encoder, container, output)

        pipeline.set_state(gst.STATE_PLAYING)
        while True:
            if source.get_property('index') <= no_files:
                if self.verbose:
                    LOG.debug("Currently processing image number: %s",
                              source.get_property('index'))
                time.sleep(1)
            else:
                break
        time.sleep(3)
        pipeline.set_state(gst.STATE_NULL)


def get_video_maker_klass():
    try:
        return GiEncoder()
    except ValueError:
        return GstEncoder()


def video_maker(input_dir, output_file):
    """
    Instantiates the encoder and encodes the input dir.
    """
    v = get_video_maker_klass()
    v.encode(input_dir, output_file)


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print('Usage: %s <input_dir> <output_file>' % sys.argv[0])
    else:
        video_maker(sys.argv[1], sys.argv[2])
