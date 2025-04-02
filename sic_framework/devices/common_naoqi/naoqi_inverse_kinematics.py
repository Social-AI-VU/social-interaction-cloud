import math

from sic_framework import SICComponentManager, utils, SICActuator
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import AudioMessage, SICConfMessage, SICMessage, SICRequest
from sic_framework.core.sensor_python2 import SICSensor

import numpy as np

if utils.PYTHON_VERSION_IS_2:
    from naoqi import ALProxy
    import qi


class ImagePointToRelativePointRequest(SICRequest):
    """
    Convert image coordinates of a point in the image _on the floor_ to coordinates relative to the robot, by
    means of inverse kinematics. Knowing the position of the camera due to the known robot measurements and measured
    joint positions, we can calculate the position of a point using trigonometry. This is very fast, but subject to
    error due to the robot's joints not being perfectly accurate, and these tiny errors multiply in the result.

    NOTE: This assumes the ground is flat and both the robot and the point in the image are on the floor.

    E.g. This can be used to estimate how far someone is from the robot, if we know where their feet are in the image.

    x, y in normalized coordinates. (0,0) is the center of the image, (-1.0, -1.0) is the top left. (1.0, 1.0) is the bottom right.
    sensor_name: the naoqi camera name in which the point was detected. One of: 'CameraBottom', 'CameraStereo', 'CameraTop'
    """

    def __init__(self, x, y, sensor_name):
        super().__init__()
        self.x = x
        self.y = y

        assert sensor_name in ['CameraBottom', 'CameraStereo', 'CameraTop']
        self.sensor_name = sensor_name

    @staticmethod
    def from_xy(x_px, y_px, W, H, sensor_name):
        """
        Convert from pixel coordinates to normalized coordinates.
        :param W: Image width
        :param H: Image height
        :return:
        """
        # rescale to range -1, 1
        x = (x_px / W) * 2 - 1
        y = (y_px / H) * 2 - 1
        return ImagePointToRelativePointRequest(x, y, sensor_name)

class RelativePointMessage(SICMessage):
    """
    The global coordinates of a point relative to the robot, in meters. (0,0,0) is the robot's base
    (the midpoint on the floor).
    x - Distance along the X axis (forward) in meters.
    y - Distance along the Y axis (side) in meters.
    z - Distance along the Z axis (up) in meters.
    """

    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

    def l2_norm(self):
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

class NaoqiInverseKinematicsComponent(SICComponent):
    @staticmethod
    def LinePlaneCollision(planeNormal, planePoint, rayDirection, rayPoint, epsilon=1e-6):
        """

        :param planeNormal: 4x1 np.array (x, y, z, 1)
        :param planePoint: 4x1 np.array (x, y, z, 1)
        :param rayDirection:  4x1 np.array (x, y, z, 1)
        :param rayPoint:  4x1 np.array (x, y, z, 1)
        :param epsilon:
        :return: 4x1 np.array (x, y, z, 1), may return None
        """

        ndotu = planeNormal.T.dot(rayDirection)
        ndotu = ndotu[0, 0]
        if abs(ndotu) < epsilon:
            return np.full((4, 1), np.nan)

        w = rayPoint - planePoint
        si = -planeNormal.T.dot(w) / ndotu
        si = si[0, 0]
        Psi = w + si * rayDirection + planePoint
        return Psi

    def __init__(self, *args, **kwargs):
        super(NaoqiInverseKinematicsComponent, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect('tcp://127.0.0.1:9559')

        self.motion_service = self.session.service('ALMotion')
        self.video_service = self.session.service("ALVideoDevice")

        self.FRAME_ROBOT = 2  # FRAME_ROBOT (the robot's base frame)
        self.use_sensor_values = True  # Use sensor values to compute the transform

    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return SICMessage

    def on_request(self, request):


        if request.sensor_name == 'CameraBottom' or request.sensor_name == 'CameraTop':
            h_fov = 56.3
            v_fov = 43.7

        elif request.sensor_name == 'CameraStereo':
            h_fov = 96
            v_fov = 60
        else:
            raise ValueError("Invalid sensor name")

        # compute the focal length factor from the field of view
        f_x = np.tan(np.deg2rad(h_fov / 2))
        f_y = np.tan(np.deg2rad(v_fov / 2))

        f_x = -f_x # mirror the image
        f_y = -f_y # mirror the image

        camera_frame_transform = self.motion_service.getTransform(request.sensor_name, self.FRAME_ROBOT,
                                                                  self.use_sensor_values)
        camera_frame_transform = np.array(camera_frame_transform).reshape((4, 4))

        # Sympy equivalent code with very slow solve.

        # M = Matrix(camera_frame_transform.tolist())
        # plane = Plane(Point3D(0, 0, 0), normal_vector=(0, 0, 1))
        # camera_origin_global = Point3D(0, 0, 0).transform(M).evalf()
        # camera_point_global = Point3D(1, camera_x, camera_y).transform(M).evalf()
        # line = Line3D(camera_origin_global, camera_point_global)
        # intersection = np.array(plane.intersection(line)).astype(float)[0]
        # x, y, z = intersection

        camera_x = request.x * f_x
        camera_y = request.y * f_y

        plane_normal = np.array([[0, 0, 1, 1]]).T
        plane_point = np.array([[0, 0, 0, 1]]).T

        camera_point = np.array([[1, camera_x, camera_y, 1]]).T
        camera_point_global = np.dot(camera_frame_transform, camera_point)
        camera_origin_global = np.dot(camera_frame_transform, np.array([[0, 0, 0, 1]]).T)

        ray_direction_global = camera_point_global - camera_origin_global

        solution = self.LinePlaneCollision(plane_normal, plane_point, ray_direction_global, camera_origin_global)

        x, y, z, _ = solution[:, 0]

        # To the right of the robot is positive y, so flip the sign
        y = -y

        reply = RelativePointMessage(x, y, z)

        return reply


class NaoqiInverseKinematics(SICConnector):
    component_class = NaoqiInverseKinematicsComponent


if __name__ == '__main__':
    SICComponentManager([NaoqiInverseKinematicsComponent])
