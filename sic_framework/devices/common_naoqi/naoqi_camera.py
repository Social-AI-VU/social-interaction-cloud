import argparse
from sic_framework import SICComponentManager, SICService, utils

from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import CompressedImageMessage, SICConfMessage, SICMessage
from sic_framework.core.sensor_python2 import SICSensor

if utils.PYTHON_VERSION_IS_2:
    from PIL import Image
    import numpy as np
    import random
    import cv2

    from naoqi import ALProxy
    import qi


class NaoqiCameraConf(SICConfMessage):
    def __init__(self, naoqi_ip='127.0.0.1', port=9559, cam_id=0, res_id=2, fps=30, brightness=None, contrast=None,
                 saturation=None, hue=None, gain=None, hflip=None, vflip=None, auto_exposition=None,
                 auto_white_bal=None, manual_exposure_val=None, auto_exp_algo=None, sharpness=None, back_light_comp=None, auto_focus=None,
                 manual_focus_value=None):
        """
        params can be found at http://doc.aldebaran.com/2-8/family/nao_technical/video_naov6.html#naov6-video
        and also
        http://doc.aldebaran.com/2-1/family/robots/video_robot.html

        Camera ID:
        0 - TopCamera
        1 - BottomCamera

        Resolution ID:
        1  -  320x240px
        2  -  640x480px
        3  -  1280x960px
        4  -  2560x1920px

        Parameter Defaults:
        brightness: 55
        contrast: 32
        saturation: 128
        hue: 0
        gain: 32
        hflip: 0
        vflip: 0
        auto_exposition: 1
        auto_white_bal: 1
        auto_exp_algo: 1
        sharpness: 0
        back_light_comp: 1
        auto_focus: 0
        manual_focus_value: 0
        """

        SICConfMessage.__init__(self)
        self.naoqi_ip = naoqi_ip
        self.port = port
        self.cam_id = cam_id
        self.res_id = res_id
        self.color_id = 11  # RGB
        self.fps = fps
        self.brightness = brightness
        self.contrast = contrast
        self.saturation = saturation
        self.hue = hue
        self.gain = gain
        self.hflip =hflip
        self.vflip = vflip
        self.auto_exposition = auto_exposition
        self.auto_white_bal = auto_white_bal
        self.manual_exposure_val = manual_exposure_val
        self.auto_exp_algo = auto_exp_algo
        self.sharpness = sharpness
        self.back_light_comp = back_light_comp
        self.auto_focus = auto_focus
        self.manual_focus_value = manual_focus_value


class BaseNaoqiCameraSensor(SICSensor):
    def __init__(self, *args, **kwargs):
        super(BaseNaoqiCameraSensor, self).__init__(*args, **kwargs)

        self.s = qi.Session()
        self.s.connect('tcp://{}:{}'.format(self.params.naoqi_ip, self.params.port))

        self.video_service = self.s.service("ALVideoDevice")

        # Dont actively set default parameters, this causes weird behaviour because the parameters are ususally not at the documented default.
        if self.params.brightness is not None: self.video_service.setParameter(self.params.cam_id, 0, self.params.brightness)
        if self.params.contrast is not None: self.video_service.setParameter(self.params.cam_id, 1, self.params.contrast)
        if self.params.saturation is not None: self.video_service.setParameter(self.params.cam_id, 2, self.params.saturation)
        if self.params.hue is not None: self.video_service.setParameter(self.params.cam_id, 3, self.params.hue)
        if self.params.gain is not None: self.video_service.setParameter(self.params.cam_id, 6, self.params.gain)
        if self.params.hflip is not None: self.video_service.setParameter(self.params.cam_id, 7, self.params.hflip)
        if self.params.vflip is not None: self.video_service.setParameter(self.params.cam_id, 8, self.params.vflip)
        if self.params.auto_exposition is not None: self.video_service.setParameter(self.params.cam_id, 11, self.params.auto_exposition)
        if self.params.auto_white_bal is not None: self.video_service.setParameter(self.params.cam_id, 12, self.params.auto_white_bal)
        if self.params.manual_exposure_val is not None: self.video_service.setParameter(self.params.cam_id, 12, self.params.manual_exposure_val)
        if self.params.auto_exp_algo is not None: self.video_service.setParameter(self.params.cam_id, 22, self.params.auto_exp_algo)
        if self.params.sharpness is not None: self.video_service.setParameter(self.params.cam_id, 24, self.params.sharpness)
        if self.params.back_light_comp is not None: self.video_service.setParameter(self.params.cam_id, 34, self.params.back_light_comp)
        if self.params.auto_focus is not None: self.video_service.setParameter(self.params.cam_id, 40, self.params.auto_focus)
        if self.params.manual_focus_value is not None: self.video_service.setParameter(self.params.cam_id, 43, self.params.manual_focus_value)
        self.video_service.setParameter(0, 35, 1)  # Keep Alive parameter

        self.videoClient = self.video_service.subscribeCamera("Camera_{}".format(random.randint(0, 100000)),
                                                              self.params.cam_id,
                                                              self.params.res_id,
                                                              self.params.color_id,
                                                              self.params.fps)

    @staticmethod
    def get_conf():
        return NaoqiCameraConf()

    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return CompressedImageMessage

    def execute(self):
        # get the actual image from the NaoImage type
        naoImage = self.video_service.getImageRemote(self.videoClient)
        imageWidth = naoImage[0]
        imageHeight = naoImage[1]
        array = naoImage[6]
        image_string = str(bytearray(array))

        # Create a PIL Image from our pixel array.
        im = Image.frombytes("RGB", (imageWidth, imageHeight), image_string)
        return CompressedImageMessage(np.asarray(im))

    def stop(self, *args):
        super(BaseNaoqiCameraSensor, self).stop(*args)
        print("Stopping NAOqi video service")
        self.video_service.shutdown()


##################
# Top Camera
##################

class NaoqiTopCameraSensor(BaseNaoqiCameraSensor):
    def __init__(self, *args, **kwargs):
        super(NaoqiTopCameraSensor, self).__init__(*args, **kwargs)

    @staticmethod
    def get_conf():
        return NaoqiCameraConf(cam_id=0, res_id=1)


class NaoqiTopCamera(SICConnector):
    component_class = NaoqiTopCameraSensor


##################
# Bottom Camera
##################

class NaoqiBottomCameraSensor(BaseNaoqiCameraSensor):
    def __init__(self, *args, **kwargs):
        super(NaoqiBottomCameraSensor, self).__init__(*args, **kwargs)

    @staticmethod
    def get_conf():
        return NaoqiCameraConf(cam_id=1, res_id=1)


class NaoqiBottomCamera(SICConnector):
    component_class = NaoqiBottomCameraSensor


##################
# Stereo Pepper Camera
##################

class StereoImageMessage(SICMessage):
    _compress_images = True

    def __init__(self, left, right, calib_params):
        self.left_image = left
        self.right_image = right

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

    def _undistort(self, img):
        import cv2

        assert self.K is not None, "Calibration parameter K not set"
        assert self.D is not None, "Calibration parameter D not set"
        return cv2.undistort(img, self.K, self.D, None, self.cameramtrx)

    def _warp(self, img, is_left):
        import cv2

        H_matrix = self.H1 if is_left else self.H2
        assert H_matrix is not None, "Calibration parameter H1 or H2 not set"
        return cv2.warpPerspective(img, H_matrix, img.shape[::-1])

    def _rectify_helper(self, img, is_left):
        import numpy as np

        if len(img.shape) == 2:
            return self._warp(self._undistort(img), is_left)

        img = np.concatenate([self._rectify_helper(img[..., i], is_left)[..., np.newaxis] for i in range(img.shape[-1])], axis=2)
        return img

    def rectify(self):

        self.left_image = self._rectify_helper(self.left_image, is_left=True)
        self.right_image = self._rectify_helper(self.right_image, is_left=False)


class NaoStereoCameraConf(NaoqiCameraConf):
    def __init__(self, calib_params=None, naoqi_ip='127.0.0.1', port=9559, cam_id=3, res_id=15, color_id=11, fps=30,
                 convert_bw=True):
        super(NaoStereoCameraConf, self).__init__(naoqi_ip, port, cam_id, res_id, color_id, fps)

        """
        Resolution ID:
        13 = 2560x720px
        14 = 1280x360px
        15 = 640x180px
        16 = 320x90px
        17 = 160x45px
        """

        if calib_params is None:
            calib_params = {}

        self.cameramtrx = calib_params.get('cameramtrx', None)
        self.K = calib_params.get('K', None)
        self.D = calib_params.get('D', None)
        self.H1 = calib_params.get('H1', None)
        self.H2 = calib_params.get('H2', None)
        self.convert_bw = convert_bw  # Convert images to b&w before sending


class StereoPepperCameraSensor(BaseNaoqiCameraSensor):
    def __init__(self, *args, **kwargs):
        super(StereoPepperCameraSensor, self).__init__(*args, **kwargs)

    @staticmethod
    def get_conf():
        return NaoStereoCameraConf()

    def execute(self):
        # Get the regular stereo image
        img_message = super(StereoPepperCameraSensor, self).execute().image

        if self.params.convert_bw:
            img_message = cv2.cvtColor(img_message, cv2.COLOR_BGR2GRAY)

        # Split the stereo image into separate left and right images
        left, right = img_message[:, :img_message.shape[1] // 2, ...], img_message[:, img_message.shape[1] // 2:, ...]

        calib_params = {"cameramtrx": self.params.cameramtrx,
                        "K": self.params.K,
                        "D": self.params.D,
                        "H1": self.params.H1,
                        "H2": self.params.H2}
        return StereoImageMessage(left, right, calib_params)

    @staticmethod
    def get_output():
        return StereoImageMessage


class StereoPepperCamera(SICConnector):
    component_class = StereoPepperCameraSensor


##################
# Depth Pepper Camera
##################

class DepthPepperCameraSensor(BaseNaoqiCameraSensor):
    def __init__(self, *args, **kwargs):
        super(DepthPepperCameraSensor, self).__init__(*args, **kwargs)

    @staticmethod
    def get_conf():
        return NaoqiCameraConf(cam_id=2, res_id=10)


class DepthPepperCamera(SICConnector):
    component_class = DepthPepperCameraSensor


if __name__ == '__main__':
    SICComponentManager([NaoqiTopCameraSensor, NaoqiBottomCameraSensor])
