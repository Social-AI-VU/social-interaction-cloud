from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.devices.common_naoqi.naoqi_camera import StereoImageMessage
from sic_framework import UncompressedImageMessage, SICRequest
from sic_framework import SICComponentManager, SICService, SICMessage, SICConfMessage, utils
from cv2 import StereoSGBM_create, ximgproc

import numpy as np

class StereoImageRequest(StereoImageMessage, SICRequest):
    def __init__(self,  *args, **kwargs):
        StereoImageMessage.__init__(self, *args, **kwargs)
        SICRequest.__init__(self)


class DepthEstimationService(SICComponent):
    INVALID_VALUE = np.nan

    def __init__(self, *args, **kwargs):
        super(DepthEstimationService, self).__init__(*args, **kwargs)

        MIN_DISP = -16
        NUM_DISP = 80  # 128  # 128 for high res, 80 for low res
        BLOCK_SIZE = 6  # 10  # 10 for high res, 6 for low res
        UNIQUENESS_RATIO = 5
        SPECKLE_WINDOW = 200
        SPECKLE_RANGE = 2
        DISP12_MAX_DIFF = 0
        STEREO_MODE = 3
        LAMBDA = 1000.0
        SIGMA_COLOR = 1.5

        self.left_matcher = StereoSGBM_create(
            minDisparity=MIN_DISP,
            numDisparities=NUM_DISP,
            blockSize=BLOCK_SIZE,
            uniquenessRatio=UNIQUENESS_RATIO,
            speckleWindowSize=SPECKLE_WINDOW,
            speckleRange=SPECKLE_RANGE,
            disp12MaxDiff=DISP12_MAX_DIFF,
            P1=8 * BLOCK_SIZE * BLOCK_SIZE,
            P2=32 * BLOCK_SIZE * BLOCK_SIZE,
            mode=STEREO_MODE
        )
        self.right_matcher = ximgproc.createRightMatcher(self.left_matcher)
        self.wls_filter = ximgproc.createDisparityWLSFilter(self.left_matcher)
        self.wls_filter.setLambda(LAMBDA)
        self.wls_filter.setSigmaColor(SIGMA_COLOR)

    @staticmethod
    def get_inputs():
        return [StereoImageMessage, StereoImageRequest]

    @staticmethod
    def get_output():
        return UncompressedImageMessage

    @staticmethod
    def disp_to_cm(disp):
        return (30 * 78) / (disp + 1e-5)

    def on_message(self, message):
        output = self.execute(message)
        self.output_message(output)

    def on_request(self, request):
        return self.execute(request)

    def execute(self, stereo_msg: StereoImageMessage):
        # Notice that the images are already rectified by StereoPepperCamera
        left, right = stereo_msg.left_image, stereo_msg.right_image

        # Calculate combined left-to-right and right-to-left disparities
        left_disp = self.left_matcher.compute(left, right)
        right_disp = self.right_matcher.compute(right, left)

        filtered_disp = self.wls_filter.filter(left_disp, left, disparity_map_right=right_disp)
        disparity_img = filtered_disp.astype(float) / 16.0

        # return UncompressedImageMessage(disparity_img)

        # disparity_img = SICservice.crop_image(disparity_img)
        disparity_img[disparity_img < 0] = self.INVALID_VALUE  # Disparity cannot be negative
        disparity_img[disparity_img >= left.shape[1]] = self.INVALID_VALUE  # Disparity larger than image width is not possible

        depth_img = self.disp_to_cm(disparity_img)  # Disparity values to cm
        depth_img[depth_img < 0] = self.INVALID_VALUE  # Depth cannot be negative
        depth_img[depth_img > 2000] = self.INVALID_VALUE  # Max distance
        return UncompressedImageMessage(depth_img)


class DepthEstimation(SICConnector):
    component_class = DepthEstimationService


if __name__ == '__main__':
    SICComponentManager([DepthEstimationService], "local")
