from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage
from sic_framework.core.sensor_python2 import SICSensor


class ReachyMiniIMUMessage(SICMessage):
    """IMU data from Reachy Mini's wireless variant.

    :param accelerometer: Accelerometer readings (x, y, z).
    :param gyroscope: Gyroscope readings (x, y, z).
    :param quaternion: Orientation quaternion (w, x, y, z).
    :param temperature: Sensor temperature.
    """

    def __init__(self, accelerometer, gyroscope, quaternion, temperature):
        self.accelerometer = accelerometer
        self.gyroscope = gyroscope
        self.quaternion = quaternion
        self.temperature = temperature


class ReachyMiniIMUConf(SICConfMessage):
    pass


class ReachyMiniIMUSensor(SICSensor):
    """Reachy Mini IMU sensor component (wireless variant only).

    Uses the singleton Reachy Mini SDK instance created by `ReachyMiniDevice`
    (stored on `ReachyMiniDevice._mini_instance`) to read `mini.imu` and emit
    a `ReachyMiniIMUMessage`.
    """

    def __init__(self, *args, **kwargs):
        super(ReachyMiniIMUSensor, self).__init__(*args, **kwargs)
        from sic_framework.devices.reachy_mini import ReachyMiniDevice

        self.mini = ReachyMiniDevice._mini_instance

    @staticmethod
    def get_conf():
        return ReachyMiniIMUConf()

    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return ReachyMiniIMUMessage

    def execute(self):
        try:
            imu = self.mini.imu
        except Exception as e:
            self.logger.warning("Failed to read IMU: {}".format(e))
            return None

        if imu is None:
            return None

        return ReachyMiniIMUMessage(
            accelerometer=imu.get("accelerometer"),
            gyroscope=imu.get("gyroscope"),
            quaternion=imu.get("quaternion"),
            temperature=imu.get("temperature"),
        )

    def _cleanup(self):
        pass


class ReachyMiniIMU(SICConnector):
    component_class = ReachyMiniIMUSensor
    component_group = "ReachyMini"


if __name__ == "__main__":
    SICComponentManager([ReachyMiniIMUSensor], component_group="ReachyMini")
