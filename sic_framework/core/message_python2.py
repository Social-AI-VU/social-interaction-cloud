"""
message_python2.py

This module contains the SICMessage class, which is the base class for all messages in the SIC framework.
"""

import io
import os
import random
import time

import numpy as np
import six

from . import utils
from google.protobuf.json_format import ParseDict, MessageToDict
from .protobuf import sic_pb2
import json
import importlib

from turbojpeg import TurboJPEG
jpeg = TurboJPEG()


if not six.PY3:
    import cPickle as pickle

    # Set path manually on pepper and nao
    lib_turbo_jpeg_path = (
        "/"
        + os.path.join(*__file__.split(os.sep)[:-3])
        + "/lib/libturbojpeg/lib32/libturbojpeg.so.0"
    )
else:
    lib_turbo_jpeg_path = None
    import pickle

try:
    from turbojpeg import TurboJPEG

    turbojpeg = TurboJPEG(lib_turbo_jpeg_path)
except (RuntimeError, ImportError):
    # fall back to PIL in case TurboJPEG is not installed
    # PIL _can_ use turbojpeg, but can also fall back to a slower libjpeg
    # it is recommended to install turbojpeg
    print("Turbojpeg not found, falling back to PIL")
    from PIL import Image

    class FakeTurboJpeg:
        def encode(self, array):
            output = io.BytesIO()
            image = Image.fromarray(array)
            image.save(output, format="JPEG")
            output.seek(0)
            return output.read()

        def decode(self, bytes):
            image = Image.open(io.BytesIO(bytes))
            image = np.array(image)
            image = np.flipud(image)[:, :, ::-1]
            return image

    turbojpeg = FakeTurboJpeg()

def dynamic_import(full_path):
    """Load a symbol dynamically from a string like 'google.cloud.dialogflow_v2.types.AudioEncoding'"""
    module_path, _, attr_path = full_path.rpartition('.')
    module = importlib.import_module(module_path)
    return getattr(module, attr_path)

# Registry and decorator to map protobuf field names to python classes
# Usage: @register_message_type("field_name") above a class to store it in MESSAGE_TYPE_REGISTRY
MESSAGE_TYPE_REGISTRY = {}

def register_message_type(proto_field_name):
    def decorator(cls):
        cls._proto_field_name = proto_field_name
        MESSAGE_TYPE_REGISTRY[proto_field_name] = cls
        return cls
    return decorator


CONFIG_CLASS_REGISTRY = {}
def register_conf_class(cls):
    CONFIG_CLASS_REGISTRY[cls.__name__] = cls
    return cls



class SICMessage(object):
    """
    The abstract message structure to pass messages around the SIC framework. Supports python types, numpy arrays
    and JPEG compression using libturbo-jpeg.

    :param _compress_images: Whether to compress images.
    :type _compress_images: bool
    :param _request_id: The request id of the message.
    :type _request_id: int
    :param _timestamp: The timestamp of the message.
    :type _timestamp: float
    :param _previous_component_name: The name of the previous component that created the message.
    :type _previous_component_name: str
    """

    # timestamp of the creation date of the data at its origin, e.g. camera, but not face detection (as it uses the
    # camera data, and should be aligned with data from the same creation time.
    _timestamp = None
    # A string with the name of the previous component that created it, used to differentiate messages of the same type.
    _previous_component_name = ""
    __NP_VALUES = []
    __JPEG_VALUES = []
    __SIC_MESSAGES = []
    _compress_images = False
    # this request id must be set when the message is sent as a reply to a SICRequest
    _request_id = None
    _proto_cls = None

    def to_proto(self):
        if not self._proto_cls:
            raise NotImplementedError("Subclasses must define _proto_cls")

        pb_msg = self._proto_cls()
        
        for field_descriptor in pb_msg.DESCRIPTOR.fields:
            field_name = field_descriptor.name
            value = getattr(self, field_name, None)
            if value is None:
                continue

            if field_descriptor.message_type:
                # nested proto message
                if isinstance(value, SICMessage):
                    nested_proto = value.to_proto()
                    # copying the nested_proto into the contents of pb_msg.field_name
                    getattr(pb_msg, field_name).CopyFrom(nested_proto)
                else:
                    # maybe value is a dict?
                    # parses a python dictionary (or JSON-like dict) and populates a protobuf message instance with its contents.
                    ParseDict(value, getattr(pb_msg, field_name))
            else:
                setattr(pb_msg, field_name, value)
        return pb_msg

    # converts a protobuf message to a dict, including nested fields
    @classmethod
    def proto_to_kwargs(self, proto_msg):
        return MessageToDict(proto_msg, preserving_proto_field_name=True)

    # construct an instance of the message class from a protobuf message
    @classmethod
    def from_proto(cls, proto_msg):
        kwargs = cls.proto_to_kwargs(proto_msg)
        return cls(**kwargs)

    @classmethod
    def get_message_name(cls):
        """
        The pretty name of this message class.

        :return: The name of the message class.
        :rtype: str
        """
        return cls.__name__

    def serialize(self):
        """
        Serialize this object into a protobuf message.

        The resulting protobuf message includes the payload field and common metadata
        such as timestamp, previous component name, and request ID.

        Raises:
            ValueError: If the object does not define a `_proto_field_name`.

        Returns:
            bytes: The serialized protobuf message.
        """
        pb_msg = sic_pb2.SICMessageProto()

        if hasattr(self, "_proto_field_name"):
            payload_field = self._proto_field_name
            payload_msg = self.to_proto()
            getattr(pb_msg, payload_field).CopyFrom(payload_msg)
        else:
            raise ValueError(f"Object {self} has no _proto_field_name")
        
        # fill the rest of the fields that are common to all messages
        if self._timestamp is None:
            pb_msg.timestamp = 0
        elif isinstance(self._timestamp, tuple):
            seconds, micros = self._timestamp
            pb_msg.timestamp = seconds  # or int(seconds + micros / 1e6), depending on your timestamp field type
        else:
            pb_msg.timestamp = int(self._timestamp)

        pb_msg.previous_component_name = getattr(self, "_previous_component_name", "")

        if hasattr(self, "_request_id") and self._request_id is not None:
            pb_msg.request_id = self._request_id

        return pb_msg.SerializeToString()
    

    @classmethod
    def deserialize(cls, data: bytes):
        """
        Deserialize a protobuf byte string into a SICMessage object (or subclass).

        Raises:
            ValueError: If no payload field is set or if the payload field is not registered.

        Args:
            data (bytes): The serialized protobuf message.

        Returns:
            SICMessage: An instance of the appropriate SICMessage subclass.
        """
        # Deserialize the raw protobuf bytes into the pb_msg object
        pb_msg = sic_pb2.SICMessageProto()
        pb_msg.ParseFromString(data)

        payload_field = pb_msg.WhichOneof("payload")

        if payload_field is None:
            raise ValueError("No payload set in SICMessageProto, need to define a payload field in sic.proto")
        
        # check if the payload_field is registered in the MESSAGE_TYPE_REGISTRY
        # if yes, use the class from the registry
        cls = MESSAGE_TYPE_REGISTRY.get(payload_field)
        if cls is None:
            raise ValueError(f"Unknown message type: {payload_field}")

        # use getattr to get the actual payload message dynamically
        payload = getattr(pb_msg, payload_field)

        # use class method to parse proto message into your Python object
        # this will call the class’s own from_proto method
        # if the class does not define it, the base class SICMessage.from_proto will be used
        obj = cls.from_proto(payload)
        # fill out other common metadata
        obj._timestamp = pb_msg.timestamp
        obj._previous_component_name = pb_msg.previous_component_name
        obj._request_id = pb_msg.request_id
 
        return obj

    @staticmethod
    def _np2base(inp):
        """
        Convert numpy arrays to byte arrays.

        :param inp: a numpy array
        :type inp: np.ndarray
        :return: the byte string
        """
        mem_stream = io.BytesIO()
        np.save(mem_stream, inp)
        return mem_stream.getvalue()

    @staticmethod
    def _base2np(inp):
        """
        Convert back from byte arrays to numpy arrays.

        :param inp: a byte string
        :type inp: bytes
        :return: the numpy array
        """
        memfile = io.BytesIO()
        memfile.write(inp)
        memfile.seek(0)
        return np.load(memfile)

    @staticmethod
    def np2jpeg(inp):
        """
        Convert numpy array to JPEG bytes.

        :param inp: a numpy array
        :type inp: np.ndarray
        :return: the JPEG bytes
        """
        return turbojpeg.encode(inp)

    @staticmethod
    def jpeg2np(inp):
        """
        Convert JPEG bytes to numpy array.

        :param inp: a JPEG bytes
        :type inp: bytes
        :return: the numpy array
        """
        # takes about 15 ms for 1280x960px
        img = turbojpeg.decode(inp)

        # the img np array now has the following flags:
        # C_CONTIGUOUS : False
        # OWNDATA: False

        # cv2 drawing functions fail, with cryptic type errors (but cv2.imShow does not)
        # the np.array() sets these flags to true
        # takes about 1 ms for 1280x960px
        img = np.array(img)

        return img

    def get_previous_component_name(self):
        """
        Get the name of the previous component that created the message.

        :return: The name of the previous component.
        :rtype: str
        """
        return self._previous_component_name


    def __eq__(self, other):
        """
        Loose check to compare if messages are the same type. type(a) == type(b) might not work because the messages
        might have been created on different machines.

        :param other: The other message to compare to.
        :type other: SICMessage
        :return: Whether the messages are the same type.
        :rtype: bool
        """
        if hasattr(other, "get_message_name"):
            return self.get_message_name() == other.get_message_name()
        else:
            return False

    def __repr__(self):
        """
        Get a string representation of this message.

        :return: The string representation of this message.
        :rtype: str
        """
        max_len = 20
        out = str(self.__class__.__name__) + "\n"

        for attr in sorted(vars(self)):
            if attr.startswith("__"):
                continue

            attr_value = str(getattr(self, attr))
            out += " " + attr + ":" + attr_value[:max_len]

            if len(attr_value) > max_len:
                out += "[...]"

            out += "\n"

        return out


######################################################################################
#                             Message types                                          #
######################################################################################

@register_message_type("sic_conf_message")
class SICConfMessage(SICMessage):
    _proto_cls = sic_pb2.SICConfMessageProto

    def to_proto(self):
        pb_msg = self._proto_cls()
        # store the class name in the config field for serialization and deserialization
        pb_msg.config["_conf_class"] = f"{self.__class__.__module__}.{self.__class__.__name__}"
        for key, value in self.__dict__.items():
            if isinstance(value, (int, float, str, bool)):
                    print(type(key), type(value))
                    pb_msg.config[key] = str(value)
        return pb_msg

    @classmethod
    def from_proto(cls, proto_msg):
        class_name = proto_msg.config.get("_conf_class")
        actual_cls = dynamic_import(class_name) if class_name else cls
        obj = actual_cls.__new__(actual_cls)

        # print("Deserializing SICConfMessage with class:", actual_cls)
        for k, v in proto_msg.config.items():
            # Skip the class name key
            if k == "_conf_class":
                continue
            try:
                val = json.loads(v)  # Handles dict, list, numbers, strings
            except (json.JSONDecodeError, TypeError):
                val = infer_type(v)  # Fallback for string → int/float/bool
            setattr(obj, k, val)


        return obj

class SICRequest(SICMessage):
    """
    A type of message that must be met with a reply, a SICMessage with the same request id, on the same channel.
    """

    _request_id = None

    def __init__(self, request_id=None):
        if request_id is not None:
            self._request_id = request_id
        else:
            # Use a large random int as default request_id
            self._request_id = random.randint(1, 2**63 - 1)


class SICControlMessage(SICMessage):
    """
    Superclass for all messages that are related to component control
    """


class SICControlRequest(SICRequest):
    """
    Superclass for all requests that are related to component control
    """


@register_message_type("sic_ping_request")
class SICPingRequest(SICControlRequest):
    """
    A request for a ping to check if alive.
    """
    _proto_cls = sic_pb2.SICPingRequestProto

@register_message_type("sic_pong_message")
class SICPongMessage(SICControlMessage):
    """
    A pong to reply to a ping request.;
    """
    _proto_cls = sic_pb2.SICPongMessageProto

@register_message_type("sic_success_message")

class SICSuccessMessage(SICControlMessage):
    """
    Special type of message to signal a request was successfully completed.
    """
    _proto_cls = sic_pb2.SICSuccessMessageProto


class SICStopRequest(SICControlRequest):
    """
    Special type of message to signal a device it should stop as the user no longer needs it.
    """

@register_message_type("sic_ignore_request_message")
class SICIgnoreRequestMessage(SICControlMessage):
    """
    Special type of message with the request_response_id set to -1. This means it will not
    be automatically set to the id of the request this is a reply to, and in effect will
    not reply to the request as the user will ignore this reply.
    """
    _proto_cls = sic_pb2.SICIgnoreRequestMessageProto

    _request_id = -1



######################################################################################
#                             Common data formats                                    #
######################################################################################


class CompressedImage(object):
    """
    Compress WxHx3 np arrays using libturbo-jpeg to speed up network transfer of
    images. This is LOSSY JPEG compression, which means the image is not exactly the same.
    Non-image array content will be destroyed by this compression.
    """

    _compress_images = True

    def __init__(self, image):
        self.image = image

@register_message_type("compressed_image_message")
class CompressedImageMessage(CompressedImage, SICMessage):
    """
    See CompressedImage
    """
    _proto_cls = sic_pb2.CompressedImageMessageProto

    def __init__(self, *args, **kwargs):
        CompressedImage.__init__(self, *args, **kwargs)
        SICMessage.__init__(self)

    def to_proto(self):
        pb_msg = self._proto_cls()

        if isinstance(self.image, np.ndarray):

            from turbojpeg import TurboJPEG
            jpeg = TurboJPEG()
            self.image = jpeg.encode(self.image)

        if not isinstance(self.image, (bytes, bytearray)):
            raise TypeError(f"Expected bytes for image, got {type(self.image)}")

        pb_msg.jpeg_data = self.image
        # print(pb_msg)
        return pb_msg
    
    @classmethod
    def from_proto(cls, proto_msg):
        image_np = jpeg.decode(proto_msg.jpeg_data)
        return cls(image=image_np)
    

class CompressedImageRequest(CompressedImage, SICRequest):
    """
    See CompressedImage
    """

    def __init__(self, *args, **kwargs):
        CompressedImage.__init__(self, *args, **kwargs)
        SICRequest.__init__(self)


class UncompressedImageMessage(SICMessage):
    """
    Message class to send images/np array without JPEG compression. The data is
    compressed using default np.save lossless compression. In other words: the
    data does not change after compression, but this is much slower than JPEGCompressedImageMessage
    """

    _compress_images = False

    def __init__(self, image):
        self.image = image


class Audio(object):
    """
    A message that containes a _byte representation_ of pulse-code modulated (PCM) 16-bit signed little endian
    integer waveform audio data. 
    
    Integers are represented as a python byte array because this is the expected and provided data format of 
    common hardware audio hardware and libraries. For compatibility with other services ensure that your data follows 
    EXACTLY this data type. This should be the most common format, but please check your data format.

    You can convert to and from .wav files using the built-in module https://docs.python.org/2/library/wave.html
    """

    def __init__(self, waveform, sample_rate):
        self.sample_rate = sample_rate
        assert isinstance(waveform, bytes) or isinstance(
            waveform, bytearray
        ), "Waveform must be a byte array"
        self.waveform = waveform


class AudioMessage(Audio, SICMessage):
    """
    Message class to send audio data.
    """

    def __init__(self, *args, **kwargs):
        Audio.__init__(self, *args, **kwargs)
        SICMessage.__init__(self)


class AudioRequest(Audio, SICRequest):
    """
    Request class to send audio data.
    """

    def __init__(self, *args, **kwargs):
        Audio.__init__(self, *args, **kwargs)
        SICRequest.__init__(self)


class Text(object):
    """
    A simple object with a string as text.
    """

    def __init__(self, text):
        self.text = text


class TextMessage(Text, SICMessage):
    """
    Message class to send text data.
    """

    def __init__(self, *args, **kwargs):
        Text.__init__(self, *args, **kwargs)
        SICMessage.__init__(self)


class TextRequest(Text, SICRequest):
    """
    Request class to send text data.
    """

    def __init__(self, *args, **kwargs):
        Text.__init__(self, *args, **kwargs)
        SICRequest.__init__(self)


class BoundingBox(object):
    """
    Bounding box for identifying an object in an image.
    
    (x,y) represents the top-left pixel of the bounding box, and (w,h) indicates the width and height.
    Identifier can be used implementation specific to for example indicate a specific object type or detected person.
    Confidence indicates the confidence of the detection mechanism.
    """

    def __init__(self, x, y, w, h, identifier=None, confidence=None):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.identifier = identifier
        self.confidence = confidence

    def xywh(self):
        """
        Get the coordinates as a numpy array.
        
        :return: The coordinates as a numpy array.
        :rtype: np.ndarray
        """
        return np.array([self.x, self.y, self.w, self.h])

    def __str__(self):
        """
        Get a string representation of this bounding box.
        
        :return: The string representation of this bounding box.
        :rtype: str
        """
        return "BoundingBox\nxywh: {}\nidentifier: {}\nconfidence: {}".format(
            self.xywh(), self.identifier, self.confidence
        )


class BoundingBoxesMessage(SICMessage):
    """
    Message class to send multiple bounding boxes.
    """

    def __init__(self, bboxes):
        self.bboxes = bboxes

@register_message_type("sic_log_message")
class SICLogMessage(SICMessage):
    _proto_cls = sic_pb2.SICLogMessageProto

    def __init__(self, msg):
        self.msg = msg
        super(SICLogMessage, self).__init__()


@register_message_type("sic_start_component_request")
class SICStartComponentRequest(SICRequest):
    """
    A request from a user to start a component.

    :param component_name: The name of the component to start.
    :type component_name: str
    :param log_level: The logging level to use for the component.
    :type log_level: logging.LOGLEVEL
    :param conf: The configuration the component.
    :type conf: SICConfMessage
    """
    # _proto_field_name = "sic_start_component_request"
    _proto_cls = sic_pb2.SICStartComponentRequestProto

    def __init__(self, component_name, log_level, input_channel, client_id, conf=None):
        super(SICStartComponentRequest, self).__init__()
        self.component_name = component_name  # str
        self.log_level = log_level  # logging.LOGLEVEL
        self.input_channel = input_channel
        self.client_id = client_id
        self.conf = conf  # SICConfMessage

    @classmethod
    def from_proto(cls, proto_msg):
        config_map = proto_msg.conf.config
        conf_classname = config_map.get("_conf_class")
        conf_cls = CONFIG_CLASS_REGISTRY.get(conf_classname, SICConfMessage)
        conf_obj = conf_cls.from_proto(proto_msg.conf)
        return cls(
            component_name = proto_msg.component_name,
            log_level = proto_msg.log_level,
            input_channel = proto_msg.input_channel,
            client_id = proto_msg.client_id,
            conf = conf_obj,
        )
    
@register_message_type("sic_component_started_message")
class SICComponentStartedMessage(SICMessage):
    _proto_cls = sic_pb2.SICComponentStartedMessageProto
    def __init__(self, output_channel, request_reply_channel):
        self.output_channel = output_channel
        self.request_reply_channel = request_reply_channel
        super(SICComponentStartedMessage, self).__init__()
