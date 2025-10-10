import queue
import time
from ultralytics import YOLO

from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import (
    BoundingBox,
    BoundingBoxesMessage,
    CompressedImageMessage,
    CompressedImageRequest,
    SICConfMessage,
)

class ObjectDetectionConf(SICConfMessage):
    def __init__(
        self,
        model_name="yolo11n.pt",
        conf_threshold=0.25,
        iou_threshold=0.7,
        classes=None,
        verbose=False,
        frequency=2.0,
    ):
        """
        Configurations and hyperparameters for the Object Detection component. See https://docs.ultralytics.com/usage/cfg/#train-settings
        for more details.

        :param model_name: Name of the model to use (e.g., 'yolo11n.pt', 'yolov8n.pt', etc.).
        :param conf_threshold: Confidence threshold for detections.
        :param iou_threshold: IoU (Intersection over Union) threshold for Non-Maximum Suppression (NMS)
        :param classes: List of class indices to filter detections. Default is None (all classes).
        :param verbose: If True, display detailed inference logs in the terminal.
        :param frequency: Detection frequency in Hz (detections per second). Default is 2.0 (every 0.5 seconds).
        """
        SICConfMessage.__init__(self)

        self.model_name = model_name
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.classes = classes
        self.verbose = verbose
        self.frequency = frequency


"""
Yolov11 object detection based on ultralytics: https://docs.ultralytics.com/tasks/detect/
"""
class ObjectDetectionComponent(SICComponent):

    def __init__(self, *args, **kwargs):
        super(ObjectDetectionComponent, self).__init__(*args, **kwargs)
        self.model = YOLO(self.params.model_name)
        self.logger.info(f"Model loaded: {self.params.model_name}")
        self.input_message_buffer = queue.Queue()

    def start(self):
        super().start()
        
        # Calculate sleep time based on frequency (Hz -> seconds)
        sleep_time = 1.0 / self.params.frequency if self.params.frequency > 0 else 0.01

        while self._signal_to_stop.is_set() is False:
            message = self.input_message_buffer.get()
            bboxes = self.detect(message.image)
            self.output_message(bboxes)
            time.sleep(sleep_time)
        
        self._stopped.set()
        self.logger.info("Stopped producing")

    @staticmethod
    def get_inputs():
        return [CompressedImageMessage, CompressedImageRequest]

    @staticmethod
    def get_output():
        return BoundingBoxesMessage

    def get_conf(self):
        return ObjectDetectionConf()

    def on_message(self, message):
        try:
            self.input_message_buffer.get_nowait()  # remove previous message if its still there
        except queue.Empty:
            pass
        self.input_message_buffer.put(message)

    def on_request(self, request):
        return self.detect(request.image)

    def detect(self, image):
        results = self.model(image, conf=self.params.conf_threshold, iou=self.params.iou_threshold, verbose=self.params.verbose)[0]

        detections = []
        # extract raw bounding boxes and labels
        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            label = results.names[cls_id]
            bbox = BoundingBox(x1, y1, x2 - x1, y2 - y1, confidence=conf, identifier=label)
            detections.append(bbox)

        return BoundingBoxesMessage(detections)


class ObjectDetection(SICConnector):
    component_class = ObjectDetectionComponent


def main():
    SICComponentManager([ObjectDetectionComponent], name="ObjectDetection")


if __name__ == "__main__":
    main()