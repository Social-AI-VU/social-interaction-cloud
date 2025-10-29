from sic_framework import SICComponentManager, SICConfMessage, SICMessage, utils
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector

if utils.PYTHON_VERSION_IS_2:
    import qi

class PepperRightBumperMessage(SICMessage):
    def __init__(self, value):
        """
        Contains a value of 1 when the right bumper is pressed, 0 on release.
        """
        super(PepperRightBumperMessage, self).__init__()
        self.value = value

class PepperRightBumperSensor(SICComponent):
    """Emits 1 when the right bumper is pressed, 0 on release."""

    def __init__(self, *args, **kwargs):
        super(PepperRightBumperSensor, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        # Connect to AL proxies
        self.memory_service = self.session.service("ALMemory")

        self.ids = []

    @staticmethod
    def get_conf():
        return SICConfMessage()

    @staticmethod
    def get_inputs():
        return []

    @staticmethod
    def get_output():
        return PepperRightBumperMessage

    def onBumperChanged(self, value):
        self.output_message(PepperRightBumperMessage(value))

    def start(self):
        super(PepperRightBumperSensor, self).start()

        self.bumper = self.memory_service.subscriber("RightBumperPressed")
        id = self.bumper.signal.connect(self.onBumperChanged)
        self.ids.append(id)

    def stop(self, *args):
        for id in self.ids:
            self.bumper.signal.disconnect(id)
        self.session.close()
        self._stopped.set()
        super(PepperRightBumperSensor, self).stop()


class PepperRightBumper(SICConnector):
    component_class = PepperRightBumperSensor


if __name__ == "__main__":
    SICComponentManager([PepperRightBumperSensor]) 