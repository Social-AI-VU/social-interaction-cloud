from sic_framework import SICComponentManager, SICConfMessage
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICMessage, SICRequest, BoundingBox
from ultralytics import YOLO


class HumanSkeletonConf(SICConfMessage):
    """
    Configuration message that determines which model to use
    :param model: Ultralytics model to use, see https://github.com/ultralytics/ultralytics/tree/main/ultralytics/models/v8
    """

    def __init__(self, model="yolov8m-pose.pt"):
        super(SICConfMessage, self).__init__()
        self.model = model


class HumanSkeletonResponse(SICMessage):
    """
    The Ultralytics YOLO response is wrapped by this class.
    :param boxes: Ultralytics boxes object
    :param keypoints: Ultralytics keypoints object
    """
    def __init__(self, boxes, keypoints):
        super().__init__()

        self.boxes = []  # N BoundingBox objects
        for box in boxes:
            identifier = box.id.item() if box.id is not None else None
            center_x = box.xywh[0][0].item()
            center_y = box.xywh[0][1].item()
            w = box.xywh[0][2].item()
            h = box.xywh[0][3].item()
            top_left_x = center_x - w / 2
            top_left_y = center_y - h / 2
            self.boxes.append(BoundingBox(x=top_left_x, y=top_left_y, w=w, h=h, confidence=box.conf.item(), identifier=identifier))

        self.keypoints = keypoints.data.cpu().numpy()  # N x 17 x 3 (number of persons, number of keypoints, [x, y, conf])


class HumanSkeletonRequest(SICRequest):
    """
    Request to get human skeleton
    :param image: image to estimate skeleton on
    :param persist: if True, model also tracks people, if False model does not track
    """
    def __init__(self, image, persist=True):
        super().__init__()
        self.image = image
        self.persist = persist


class HumanSkeletonComponent(SICComponent):
    """
    Class to estimate skeleton of persons
    """

    def __init__(self, *args, **kwargs):
        super(HumanSkeletonComponent, self).__init__(*args, **kwargs)
        self.model = YOLO(self.params.model)  # load an official model

    @staticmethod
    def get_inputs():
        return [HumanSkeletonRequest]

    @staticmethod
    def get_output():
        return HumanSkeletonResponse

    @staticmethod
    def get_conf():
        return HumanSkeletonConf()

    def on_message(self, message):
        output = self.on_request(message)
        self.output_message(output)

    def on_request(self, request):
        output = self.model.track(request.image, persist=request.persist)
        output = HumanSkeletonResponse(boxes=output[0].boxes, keypoints=output[0].keypoints)
        return output


class HumanSkeleton(SICConnector):
    component_class = HumanSkeletonComponent


if __name__ == '__main__':
    # Request the service to start using the SICServiceManager on this device
    SICComponentManager([HumanSkeletonComponent])
