from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage
from sic_framework.core.sensor_python2 import SICSensor

class SpaceMouseStates(SICMessage):
    def __init__(self, t, x, y, z, roll, pitch, yaw, buttons):
        """
        State objects returned from read() have 7 attributes: [t,x,y,z,roll,pitch,yaw,button].
        :param t: timestamp in seconds since the script started.
        :param x: x translation in the range [-1.0, 1.0]
        :param y: y translation in the range [-1.0, 1.0]
        :param z: z translation in the range [-1.0, 1.0]
        :param roll: roll rotation in the range [-1.0, 1.0].
        :param pitch: pitch rotations in the range [-1.0, 1.0].
        :param yaw: yaw rotation in the range [-1.0, 1.0].
        :param buttons: list of button states (0 or 1), in order specified in the device specifier

        """
        SICConfMessage.__init__(self)
        self.t = t
        self.x = x
        self.y = y
        self.z = z
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
        self.buttons = buttons


class DesktopSpaceMouseSensor(SICSensor):
    def __init__(self, *args, **kwargs):
        super(DesktopSpaceMouseSensor, self).__init__(*args, **kwargs)
        import pyspacemouse as pyspacemouse
        self.spacemouse = pyspacemouse
        self.logger.info("Initializing DesktopSpaceMouseSensor")
        self.success = self.spacemouse.open(dof_callback=pyspacemouse.print_state, button_callback=pyspacemouse.print_buttons)
    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return SpaceMouseStates

    def execute(self):

        if self.success:
            state = self.spacemouse.read()
            # print(state)
        else:
            self.logger.warning("Failed to read from the space mouse")
        return SpaceMouseStates(state.t, state.x, state.y, state.z, state.roll, state.pitch, state.yaw, state.buttons)

    def stop(self, *args):
        super(DesktopSpaceMouseSensor, self).stop(*args)
        self.cam.release()


class DesktopSpaceMouse(SICConnector):
    component_class = DesktopSpaceMouseSensor


if __name__ == '__main__':
    SICComponentManager([DesktopSpaceMouseSensor])
