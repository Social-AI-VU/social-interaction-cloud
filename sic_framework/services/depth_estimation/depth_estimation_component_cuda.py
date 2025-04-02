from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.devices.common_naoqi.naoqi_camera import StereoImageMessage
from sic_framework import UncompressedImageMessage, SICRequest
from sic_framework import SICComponentManager, SICService, SICMessage, SICConfMessage, utils

import numpy as np
import vpi

class StereoImageRequest(StereoImageMessage, SICRequest):
    def __init__(self,  *args, **kwargs):
        StereoImageMessage.__init__(self, *args, **kwargs)
        SICRequest.__init__(self)

class DepthEstimationCudaComponent(SICComponent):
    INVALID_VALUE = np.nan

    def __init__(self, *args, **kwargs):
        super(DepthEstimationCudaComponent, self).__init__(*args, **kwargs)

        self.stereo_estimator = vpi.create_stereo_disparity_estimator(
            backend=vpi.Backend.CUDA,
            num_disparities=128,
            block_size=10,
            min_disparity=-16
        )

    @staticmethod
    def get_inputs():
        return [StereoImageMessage, StereoImageRequest]

    @staticmethod
    def get_output():
        return UncompressedImageMessage

    @staticmethod
    def disp_to_cm(disp):
        return (45 * 78) / (disp + 1e-5)

    def on_message(self, message):
        output = self.execute(message)
        self.output_message(output)

    def on_request(self, request):
        return self.execute(request)

    def execute(self, stereo_msg: StereoImageMessage):
        left, right = stereo_msg.left_image, stereo_msg.right_image

        with vpi.Backend.CUDA:
            left_img = vpi.asimage(left)
            right_img = vpi.asimage(right)

            disparity_map = self.stereo_estimator.compute(left_img, right_img)
            disparity_img = disparity_map.cpu().numpy().astype(float) / 16.0

        disparity_img[disparity_img < 0] = self.INVALID_VALUE
        disparity_img[disparity_img >= left.shape[1]] = self.INVALID_VALUE

        depth_img = self.disp_to_cm(disparity_img)
        depth_img[depth_img < 0] = self.INVALID_VALUE
        depth_img[depth_img > 2000] = self.INVALID_VALUE

        return UncompressedImageMessage(depth_img)

class DepthEstimationCuda(SICConnector):
    component_class = DepthEstimationCudaComponent

if __name__ == '__main__':
    SICComponentManager([DepthEstimationCudaComponent], "local")
