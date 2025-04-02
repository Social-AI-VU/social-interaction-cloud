import argparse
import logging
import subprocess
import threading
import time
import numpy as np

from sic_framework import SICComponentManager, SICService, utils
from sic_framework.core.component_python2 import SICComponent

from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import CompressedImageMessage, SICConfMessage, SICMessage
from sic_framework.core.sensor_python2 import SICSensor
from sic_framework.devices.common_naoqi.naoqi_camera import StereoImageMessage

if utils.PYTHON_VERSION_IS_2:
    from PIL import Image
    import random
    import cv2

    from naoqi import ALProxy
    import qi

"""
GStreamer can be used in place of naoqi to acces the camera to provide a much higher frame rate.
This requires you to follow these steps on your machine in order to be able to acces the video stream, as its is transfered outside of the framework.
This is not recomended unless you really need the additonal resolution or framerate

1. Uninstall opencv-python
> pip uninstall opencv-python

2. Install/Ensure you have gstreamer and plugins 
sudo apt-get install libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-qt5 gstreamer1.0-pulseaudio


3. Download, build and install opencv with GStreamer 
# <navigate to where you want the opencv-python repo to be stored>
git clone --recursive https://github.com/skvark/opencv-python.git
cd opencv-python
export CMAKE_ARGS="-DWITH_GSTREAMER=ON"  
export ENABLE_CONTRIB=1                
pip install --upgrade pip wheel
# this is the build step - the repo estimates it can take from 5 
#   mins to > 2 hrs depending on your computer hardware
pip wheel . --verbose
pip install opencv_python*.whl
# note, wheel may be generated in dist/ directory, so may have to cd first (or check the output log where it was placed, might be in /tmp/)

4. Test your installation of opencv with gstreamer with this python code:

    vid_capture = cv2.VideoCapture('videotestsrc ! appsink', cv2.CAP_GSTREAMER)
    while True:
            ret, im = vid_capture.read()
            if ret:
                    cv2.imshow("Test image", im)
                    cv2.waitKey(1)

5. Launch gstreamer on pepper/nao (you may have to reboot it first if you have already previously accesed the camera using naoqi)
# on pepper/nao:

> gst-launch-0.10 -v v4l2src device=/dev/video0 ! 'video/x-raw-yuv,width=1344,height=376,framerate=60/1' ! ffmpegcolorspace ! jpegenc ! rtpjpegpay ! udpsink host=10.0.0.149 port=3000


6. On your laptop view the stream with
port = 3000
pipeline = ('udpsrc port={} ! '
        'application/x-rtp, encoding-name=JPEG,payload=26 ! '
        'rtpjpegdepay ! '
        'queue ! jpegdec ! videoconvert ! '
        'appsink').format(port)
vid_capture = = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)


"""


class GStreamerCameraConf(SICConfMessage):
    def __init__(self,
                 gstreamer_options='video/x-raw-yuv,width=1344,height=376,framerate=60/1',
                 calib_params=None,
                 host=None, ):
        """



        video-stereo -> video0
        video-top -> video1
        video-bottom -> video2
        :type host: the ip adress of your machine

        """

        SICConfMessage.__init__(self)
        self.gstreamer_options = gstreamer_options
        self.host = host

        # Calibration parameters are sent along the image from the robot
        self._set_calib_params(calib_params)

    def _set_calib_params(self, calib_params):
        self.cameramtrx = calib_params['cameramtrx']
        self.K = calib_params['K']
        self.D = calib_params['D']
        self.H1 = calib_params['H1']
        self.H2 = calib_params['H2']

    def _get_calib_params(self):
        return {"cameramtrx": self.cameramtrx, "K": self.K, "D": self.D, "H1": self.H1, "H2": self.H2}


class BaseGStreamerCameraSensor(SICComponent):
    COMPONENT_STARTUP_TIMEOUT = 60

    def __init__(self, *args, **kwargs):
        super(BaseGStreamerCameraSensor, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect('tcp://127.0.0.1:9559')

        # self.motion = self.session.service('ALMotion')
        #
        # self.logger.info("Puttting pepper to rest")
        # self.motion.rest()
        #
        # # subprocess.call("pkill -9 naoqi-service", shell=True) # TODO maybe replace with naoqi rest or something to deactivate the cameras
        # self.logger.info("Starting streamer")

        # resolution: v4l2-ctl -d /dev/video0 --list-formats-ext

        # TODO cmd: pkill naoqi-service
        # TODO sleep 3

        ret = subprocess.call(
            "gst-launch-0.10 -v v4l2src device=/dev/video0 ! 'video/x-raw-yuv,width=1344,height=376,framerate=60/1' ! ffmpegcolorspace ! jpegenc ! rtpjpegpay ! udpsink host={} port=3000".format(
                self.params.host), shell=True)
        # ret = subprocess.call("gst-launch-0.10 -v v4l2src device=/dev/video0 ! 'video/x-raw-yuv,width=2560,height=720,framerate=60/1' ! ffmpegcolorspace ! jpegenc ! rtpjpegpay ! udpsink host={} port=3000".format(self.params.host), shell=True)

        # TODO cmd: naoqi-service

        self.logger.info(str(ret))  # TODO improve logging,
        # check with> ps -aux | grep gst-launch
        # if its up succesfully

        # self.motion.wakeUp()
        # self.logger.info("Waking pepper up")

    # v4l2-ctl -d /dev/video0 --set-fmt-video=width=2560height=720,pixelformat=YUYV

    @staticmethod
    def get_conf():
        return GStreamerCameraConf()

    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return SICMessage


class GstreamerCamera(SICConnector):
    component_class = BaseGStreamerCameraSensor

    """

    NOTE: We bypass usual SIC machinery here as the data is not sent via redis but a raw stream directly
    This connector therefore overwrites some key methods



    if you encounter

    ImportError: /usr/lib/x86_64-linux-gnu/libgobject-2.0.so.0: undefined symbol: ffi_type_uint32, version LIBFFI_BASE_7.0

    You may need

    export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libffi.so.7

    """

    def __init__(self, ip="localhost", log_level=logging.INFO, conf=None):
        self.stop_event = threading.Event()

        if conf is None:
            host_ip = utils.get_ip_adress()
            conf = GStreamerCameraConf(host=host_ip)
        elif conf.host is None:
            conf.host = utils.get_ip_adress()

        super().__init__(ip=ip, log_level=log_level, conf=conf)

        import cv2

        pipeline = 'udpsrc port=3000 ! application/x-rtp, encoding-name=JPEG,payload=26 ! rtpjpegdepay ! queue ! jpegdec ! videoconvert !  appsink'

        self.vid_capture = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

        self.t = threading.Thread(target=self.start)
        self.t.start()

        self.callback_list = []

    def __del__(self):
        self.stop_event.set()
        self.t.join()

    def start(self):
        while not self.stop_event.is_set():
            ret, img = self.vid_capture.read()
            if ret:

                stereo_message = StereoImageMessage(left=img[:, :img.shape[1] // 2, ...],
                                                    right=img[:, img.shape[1] // 2:, ...],
                                                    calib_params=self._conf._get_calib_params())

                for callback in self.callback_list:
                    threading.Thread(target=callback, args=(stereo_message,)).start()

            time.sleep(0.001)

    def register_callback(self, fn):
        """
        NOTE: We bypass SIC here as the data is not sent via redis but a raw stream directly
        """
        self.callback_list.append(fn)



