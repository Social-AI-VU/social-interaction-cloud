from sic_framework import SICComponentManager, SICConfMessage, SICRequest, SICMessage
from sic_framework.core.connector import SICConnector
from sic_framework.core.component_python2 import SICComponent

import concurrent
import queue
import time
from collections import defaultdict

import cv2
import numpy as np
import concurrent.futures
import threading

from codecs import decode
from pickle import loads

# from sic_framework.devices.common_naoqi.naoqi_camera_gstreamer import GStreamerCameraConf
from sic_framework.devices.common_naoqi.naoqi_inverse_kinematics import ImagePointToRelativePointRequest, RelativePointMessage
from sic_framework.devices.common_naoqi.naoqi_stiffness import Stiffness
from sic_framework.devices.common_naoqi.naoqi_text_to_speech import NaoqiTextToSpeechRequest
from sic_framework.services.depth_estimation import DepthEstimation, StereoImageRequest

from sic_framework.devices import Pepper
from sic_framework.devices.common_naoqi.naoqi_autonomous import NaoBasicAwarenessRequest
from sic_framework.devices.common_naoqi.naoqi_camera import NaoStereoCameraConf, StereoImageMessage
from sic_framework.devices.common_naoqi.naoqi_leds import NaoLEDRequest, NaoFadeRGBRequest
from sic_framework.devices.common_naoqi.naoqi_lookat import LookAtMessage
from sic_framework.devices.common_naoqi.naoqi_motion import PepperPostureRequest, NaoqiIdlePostureRequest
from sic_framework.services.skeleton_estimation import HumanSkeleton, HumanSkeletonRequest, HumanSkeletonResponse
from sic_framework.core.utils import is_sic_instance


class Person:
    def __init__(self, pepper):
        self.pepper = pepper
        self.person_id = None
        self.look_at_xy_px = [None, None]
        self.last_updated = 0.
        self.interaction_count = 0
        self.distance_ik = np.nan
        self.distance_depth = np.nan
        self.depth_bbox = None
        self.global_xy = [None, None]
        self.feet_xy_px = [None, None]

    def update(self, person_id, keypoints, image_w, image_h, depth_image):
        self.person_id = person_id
        nose, l_ear, r_ear = keypoints[0], keypoints[3], keypoints[4]
        xs, ys, confs = keypoints[[0, 3, 4]].T
        # Create boundingbox over
        xs, ys, confs = keypoints[[5, 6, 11, 12]].T

        try:
            if np.all(confs > .5):
                x_min = int(max(xs[[1, 3]]))
                x_max = int(min(xs[[0, 2]]))
                y_min = int(max(ys[[0, 1]]))
                y_max = int(min(ys[[2, 3]]))

                if depth_image is not None:
                    depth_patch = depth_image[y_min:y_max, x_min:x_max]

                    if depth_patch.size > 0:
                        if np.all(np.isnan(depth_patch)):
                            self.distance_depth = np.nan
                        else:
                            DEPTH_BIAS_CORRECTION = -1  # Empirical value to align with measured threshold
                            self.distance_depth = (np.nanmedian(
                                depth_patch) / 100) + DEPTH_BIAS_CORRECTION  # cm to m

                    self.depth_bbox = [x_min, y_min, x_max, y_max]

        except ValueError:
            # no keypoints visible
            pass

        # Update lookat pixel for person
        a_point_on_face = None
        if nose[0] > 0:
            a_point_on_face = nose
        elif r_ear[0] > 0:
            a_point_on_face = r_ear
        elif l_ear[0] > 0:
            a_point_on_face = l_ear
        if a_point_on_face is not None:
            self.look_at_xy_px = [float(v) for v in a_point_on_face[:2]]

        # Check if confidence of nose and ears keypoints is larger than 0.5
        see_face_front = r_ear[-1] > 0.3 and l_ear[-1] > 0.3 and nose[-1] > 0.5

        if see_face_front:
            self.interaction_count += 1

        self.last_updated = time.time()

        feet = keypoints[-1]
        if feet[0] > 0 and feet[1] > 0:
            x, y = [float(v) for v in feet[:2]]
            self.feet_xy_px = [x, y]

            ik_request = ImagePointToRelativePointRequest.from_xy(
                x, y, image_w, image_h, "CameraStereo")
            reply = self.pepper.inverse_kinematics.request(ik_request)
            self.global_xy = [reply.x, reply.y]

            IK_BIAS_CORRECTION = -1.5  # Empirical value to align with measured threshold
            self.distance_ik = reply.l2_norm() + IK_BIAS_CORRECTION


class PersonTracker:
    def __init__(self, pepper, interaction_timeout, delete_timeout):
        self.pepper = pepper
        self.interaction_timeout = interaction_timeout
        self.delete_timeout = delete_timeout

        # Store information per person
        self.persons = defaultdict(lambda: Person(pepper=self.pepper))
        self.START_TIME = time.time()

    def update(self, person_id, keypoints, image_w, image_h, depth_image):
        self.persons[person_id].update(
            person_id, keypoints, image_w, image_h, depth_image)

    def filter(self):
        current_time = time.time()

        # Filter based on last update time
        persons = list(self.persons.items())

        subset = {}
        for person_id, person_info in persons:
            should_delete = (
                current_time - person_info.last_updated) > self.delete_timeout

            if should_delete:
                del self.persons[person_id]

            should_interact = (
                current_time - person_info.last_updated) < self.interaction_timeout
            if should_interact:
                subset[person_id] = person_info

        return subset

    def get_active_person(self):
        subset = self.filter()
        if len(subset) == 0:
            return []

        active_persons = list(sorted(
            subset.items(), key=lambda item: item[1].interaction_count, reverse=True))

        return active_persons


class PersonFollowerConf(SICConfMessage):
    """
    PersonFollower SICConfMessage
    """

    def __init__(self, pepper_ip, calib_path="../services/depth_estimation/calib", interaction_timeout=0.2, delete_timeout=5):
        super(SICConfMessage, self).__init__()
        self.pepper_ip = pepper_ip
        self.calib_path = calib_path
        self.interaction_timeout = interaction_timeout
        self.delete_timeout = delete_timeout


class PersonFollowerStatus(SICRequest):
    """
    Status message to control person following behavior

    :param start_following: Whether to start or stop following
    """

    def __init__(self, is_following=True):
        super().__init__()
        self.is_following = is_following


class PersonFollowerOutputMessage(SICMessage):
    """
    PersonFollower input message
    """

    def __init__(self, image, depth_image, events):
        super(SICMessage, self).__init__()
        self.image = image
        self.depth_image = depth_image
        self.events = events


class PersonFollowerComponent(SICComponent):
    """
    PersonFollower SICAction
    """

    def __init__(self, *args, **kwargs):
        super(PersonFollowerComponent, self).__init__(*args, **kwargs)
        # Do component initialization
        self._init_personfollower()
    
    def _init_personfollower(self):
        self.is_following = True
        # Depth estimation
        with open(self.params.calib_path, "rb") as f:
            self.cameramatrix, K, D, H1, H2 = loads(decode(f.read(), 'base64'))
            self.calib_params = {"cameramtrx": self.cameramatrix,
                                 "K": K,
                                 "D": D,
                                 "H1": H1,
                                 "H2": H2
                                 }

        self.stereo_depth_service = DepthEstimation()
        self.results_buffer = queue.Queue()  
        self.depth_results_buffer = queue.Queue() 
        self.stereo_images_buffer = queue.LifoQueue() 
        self.complete_data_buffer = queue.LifoQueue() 
        # Pepper setup
        self.stereo_conf = NaoStereoCameraConf(
            calib_params=self.calib_params, convert_bw=False, res_id=14)
        # gstereo_conf = GStreamerCameraConf(calib_params=calib_params)

        self.pepper = Pepper(
            ip=self.params.pepper_ip, stereo_camera_conf=self.stereo_conf)
        # pepper = Pepper(ip=self.params.pepper_ip, stereo_camera_conf=stereo_conf, gstreamer_camera_conf=gstereo_conf)
        self.pepper.leds.request(NaoLEDRequest("FaceLeds", True))

        # Turn off basic awareness
        self.pepper.autonomous.request(NaoBasicAwarenessRequest(value=True,
                                                                stimulus_detection=[("People", False), ("TabletTouch", False),
                                                                                    ("Sound", False), (
                                                                    "Movement", False),
                                                                    ("NavigationMotion", False), ("Touch", True)]))
        self.pepper.stiffness.request(
            Stiffness(stiffness=.7, joints=["Head", "LArm", "RArm"]))
        print("Reset to stand motion")
        self.pepper.motion.request(PepperPostureRequest("Stand"))
        self.pepper.look_at.send_message(LookAtMessage(
            x=.5, y=.5, camera_index=self.stereo_conf.cam_id, speed=0.1))

        self.tracker = PersonTracker(pepper=self.pepper, interaction_timeout=self.params.interaction_timeout, delete_timeout=self.params.delete_timeout)  # Create tracker to track people
        self.skeleton_estimator = HumanSkeleton()
        # Send the camera images and the detected faces to this program
        self.pepper.stereo_camera.register_callback(self._on_stereo_image)
        # pepper._gstreamer_camera.register_callback(self._on_stereo_image)
        stereo_processing_thread = threading.Thread(target=self._process_stereo_image)
        stereo_processing_thread.start()
        # start thread
        t = threading.Thread(target=self._main_data)
        t.start()

        # use all component to ensure they are started
        self.pepper.inverse_kinematics.request(
            ImagePointToRelativePointRequest.from_xy(0, 0, 100, 100, "CameraStereo"))
        self.pepper.tts.request(NaoqiTextToSpeechRequest(
            "Ready to follow!"), block=False)
        self.depth_image_global = None

    def _on_stereo_image(self, stereo_message: StereoImageMessage):
        self.stereo_images_buffer.put(stereo_message)

    def _on_complete_data(self, stereo_message, depth_message, skeleton_message):
        events = []
        h, w, _ = stereo_message.left_image.shape

        # Update tracker
        for bbox, keypoints in zip(skeleton_message.boxes, skeleton_message.keypoints):
            if bbox.identifier is not None:
                self.tracker.update(int(bbox.identifier), keypoints,
                                    w, h, depth_message.image)

        # Get person to interact with
        persons = self.tracker.get_active_person()

        if len(persons) == 0:
            # No people detected, reset to idle
            self.pepper.motion.request(NaoqiIdlePostureRequest(
                joints="Head", value=True), block=False)
            self.pepper.motion.request(NaoqiIdlePostureRequest(
                joints="RArm", value=True), block=False)
        else:
            # Follow the most active person
            person_id, person_info = persons[0]
            x, y = person_info.look_at_xy_px
            if x is not None and y is not None:
                msg = LookAtMessage(x=float(x / w), y=float((y + 0) / h),
                                    camera_index=self.stereo_conf.cam_id, speed=0.3)
                self.pepper.look_at.send_message(msg)
                events.append("following")

        # Add visualization data for all tracked persons
        for i, (person_id, person_info) in enumerate(persons):
            # Add image to buffer for visualization
            x, y = person_info.look_at_xy_px
            if x is not None and y is not None:
                cv2.circle(stereo_message.left_image, (int(x), int(y)),
                           radius=10, color=(255, 0, 0), thickness=2)

                cv2.putText(stereo_message.left_image,
                            f"Person {person_id} ({person_info.interaction_count}f) ik({person_info.distance_ik:.2f}m) d({person_info.distance_depth:.2f}m)",
                            (int(x), int(y)), cv2.FONT_HERSHEY_PLAIN, 1,
                            (255, 0, 0), 1, cv2.LINE_AA)

            if person_info.depth_bbox is not None:
                x, y, xx, yy = person_info.depth_bbox
                cv2.rectangle(stereo_message.left_image, (x, y), (xx, yy),
                              color=(0, 0, 255), thickness=2)

            x, y = person_info.feet_xy_px
            if x is not None and y is not None:
                cv2.circle(stereo_message.left_image, (int(x), int(y)),
                           radius=10, color=(255, 0, 255), thickness=2)

        self.results_buffer.put((stereo_message.left_image, events))

    def _process_stereo_image(self):
        with concurrent.futures.ThreadPoolExecutor(2) as executor:

            while True:
                stereo_message = self.stereo_images_buffer.get()
                self.stereo_images_buffer.queue.clear()
                stereo_message.rectify()
                stereo_request = StereoImageRequest(stereo_message.left_image, stereo_message.right_image,
                                                    stereo_message._get_calib_params())
                future_depth = executor.submit(
                    self.stereo_depth_service.request, stereo_request)
                future_skeleton = executor.submit(self.skeleton_estimator.request,
                                                  HumanSkeletonRequest(image=stereo_message.left_image))
                skeleton_message = future_skeleton.result()
                depth_message = future_depth.result()
                self.depth_image_global = depth_message.image

                # once we have collected everything, process it
                self.complete_data_buffer.put(
                    (stereo_message, depth_message, skeleton_message))

    def _main_data(self):
        while True:
            stereo_message, depth_message, skeleton_message = self.complete_data_buffer.get()
            self._on_complete_data(
                stereo_message, depth_message, skeleton_message)

    @staticmethod
    def get_inputs():
        return [PersonFollowerStatus]

    @staticmethod
    def get_output():
        return PersonFollowerOutputMessage

    # This function is optional
    @staticmethod
    def get_conf():
        return PersonFollowerConf()

    def on_message(self, message):
        img, events = self.results_buffer.get()
        self.output_message(PersonFollowerOutputMessage(img, self.depth_image_global, events))

    def on_request(self, request: PersonFollowerStatus):
        img, events = self.results_buffer.get()
        return PersonFollowerOutputMessage(img, self.depth_image_global, events)


class PersonFollower(SICConnector):
    component_class = PersonFollowerComponent


if __name__ == '__main__':
    # Request the service to start using the SICServiceManager on this device
    SICComponentManager([PersonFollowerComponent])
