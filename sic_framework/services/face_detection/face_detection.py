from pathlib import Path

import cv2
import numpy as np
from numpy import array

from sic_framework.core import sic_logging
from sic_framework.core.utils_cv2 import draw_bbox_on_image
from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    BoundingBox,
    BoundingBoxesMessage,
    CompressedImageMessage,
    CompressedImageRequest,
    SICConfMessage,
    SICMessage,
)
from sic_framework.core.service_python2 import SICService


class FaceDetectionConf(SICConfMessage):
    """
    Face detection configuration.

    :param minW       Minimum possible face width in pixels. Setting this too low causes detection to be slow.
    :type minW: int
    :param minH       Minimum possible face height in pixels.
    :type minH: int
    :type minW: int
    :param merge_image  Whether to merge the image with the bounding boxes.
    :type merge_image: bool
    """
    def __init__(self, minW=150, minH=150, merge_image=False):
        SICConfMessage.__init__(self)

        # Define min window size to be recognized as a face_img
        self.minW = minW
        self.minH = minH

        # Whether to merge the image with the bounding boxes.
        self.merge_image = merge_image


class FaceDetectionComponent(SICComponent):
    def __init__(self, *args, **kwargs):
        super(FaceDetectionComponent, self).__init__(*args, **kwargs)
        script_dir = Path(__file__).parent.resolve()
        cascadePath = str(script_dir / "haarcascade_frontalface_default.xml")
        self.faceCascade = cv2.CascadeClassifier(cascadePath)

    @staticmethod
    def get_inputs():
        return [CompressedImageMessage, CompressedImageRequest]

    @staticmethod
    def get_conf():
        return FaceDetectionConf()

    @staticmethod
    def get_output():
        """
        Will return either a BoundingBoxesMessage or a CompressedImageMessage, depending on the merge_image parameter.
        If merge_image is False, the output channel will be a BoundingBoxesMessage.
        If merge_image is True, the output channel will be a CompressedImageMessage.
        """
        return [BoundingBoxesMessage, CompressedImageMessage]

    def on_message(self, message):
        self.output_message(self.detect(message.image))

    def on_request(self, request):
        return self.detect(request.image)

    def detect(self, image):
        img = array(image).astype(np.uint8)

        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        faces = self.faceCascade.detectMultiScale(
            gray,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(int(self.params.minW), int(self.params.minH)),
        )

        faces = [BoundingBox(x, y, w, h) for (x, y, w, h) in faces]

        # if merge_image is True, return the image with the bounding boxes drawn on it
        if self.params.merge_image:
            for face in faces:
                draw_bbox_on_image(face, img)
            return CompressedImageMessage(img)
        else:
            # otherwise, return the bounding boxes only
            return BoundingBoxesMessage(faces)


class FaceDetection(SICConnector):
    component_class = FaceDetectionComponent


def main():
    SICComponentManager([FaceDetectionComponent], name="FaceDetection")


if __name__ == "__main__":
    main()