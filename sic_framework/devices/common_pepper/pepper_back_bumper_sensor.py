from sic_framework import SICComponentManager, SICConfMessage, SICMessage, utils
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector

if utils.PYTHON_VERSION_IS_2:
    import qi

class PepperBackBumperMessage(SICMessage):
    def __init__(self, value):
        """
        Contains a value of 1 when the back bumper is pressed, 0 on release.
        """
        super(PepperBackBumperMessage, self).__init__()
        self.value = value

class PepperBackBumperSensor(SICComponent):
    """Emits 1 when the rear bumper is pressed, 0 on release."""

    def __init__(self, *args, **kwargs):
        super(PepperBackBumperSensor, self).__init__(*args, **kwargs)

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
        return PepperBackBumperMessage

    def onBumperChanged(self, value):
        self.output_message(PepperBackBumperMessage(value))

    def start(self):
        super(PepperBackBumperSensor, self).start()

        self.bumper = self.memory_service.subscriber("BackBumperPressed")
        id = self.bumper.signal.connect(self.onBumperChanged)
        self.ids.append(id)

    def stop(self, *args):
        for id in self.ids:
            self.bumper.signal.disconnect(id)
        self.session.close()
        self._stopped.set()
        super(PepperBackBumperSensor, self).stop()


class PepperBackBumper(SICConnector):
    component_class = PepperBackBumperSensor


if __name__ == "__main__":
    SICComponentManager([PepperBackBumperSensor])