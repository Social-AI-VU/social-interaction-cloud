from pathlib import Path

import cv2
import numpy as np
from numpy import array

from sic_framework.core import sic_logging
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
    def __init__(self, minW=150, minH=150):
        """
        :param minW       Minimum possible face width in pixels. Setting this too low causes detection to be slow.
        :param minH       Minimum possible face height in pixels.
        """
        SICConfMessage.__init__(self)

        # Define min window size to be recognized as a face_img
        self.minW = minW
        self.minH = minH


class FaceDetectionComponent(SICComponent):
    def __init__(self, *args, **kwargs):
        super(FaceDetectionComponent, self).__init__(*args, **kwargs)
        self.script_dir = Path(__file__).parent.resolve()
        self.cascadePath = str(self.script_dir / "haarcascade_frontalface_default.xml")
        self.client_models = {}
        # self.faceCascade = cv2.CascadeClassifier(cascadePath)

    @staticmethod
    def get_inputs():
        return [CompressedImageMessage, CompressedImageRequest]

    @staticmethod
    def get_conf():
        return FaceDetectionConf()

    @staticmethod
    def get_output():
        return BoundingBoxesMessage

    def on_message(self, client_info=dict(), message=""):
        self.logger.info(f"Using model for client {client_info['input_channel']}")
        model = self.client_models[client_info["input_channel"]]
        bboxes = self.detect(message.image, model)
        self.output_message(output_channel=client_info["output_channel"], message=bboxes)

    def on_request(self, request):
        return self.detect(request.image)

    def detect(self, image, model=None):
        img = array(image).astype(np.uint8)

        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        faces = model.detectMultiScale(
            gray,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(int(self.params.minW), int(self.params.minH)),
        )

        faces = [BoundingBox(x, y, w, h) for (x, y, w, h) in faces]

        return BoundingBoxesMessage(faces)

    def setup_client(self, input_channel, output_channel):
        self.logger.info(f"Defining model for client {input_channel}")
        # define a new model instance for the client
        self.client_models[input_channel] = cv2.CascadeClassifier(self.cascadePath)

        return {
            "input_channel": input_channel,
            "output_channel": output_channel,
        }


class FaceDetection(SICConnector):
    component_class = FaceDetectionComponent


def main():
    SICComponentManager([FaceDetectionComponent])


if __name__ == "__main__":
    main()
