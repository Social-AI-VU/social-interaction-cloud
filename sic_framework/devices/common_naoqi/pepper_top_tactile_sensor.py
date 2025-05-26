from sic_framework import SICComponentManager, SICConfMessage, SICMessage, utils
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector

if utils.PYTHON_VERSION_IS_2:
    import qi
# 

class PepperTactileSensorMessage(SICMessage):
    def __init__(self, value):
        """
        Contains a value of 1, indicating tactile was touched.
        http://doc.aldebaran.com/2-5/naoqi/sensors/altouch-api.html?highlight=middletactiltouched#MiddleTactilTouched
        """
        super(PepperTactileSensorMessage, self).__init__()
        self.value = value


class PepperTopTactileSensor(SICComponent):
    """
    PepperTopTactileSensor is a sensor that reads the robot's physical button and touch values from the ALMemory module.
    """

    def __init__(self, *args, **kwargs):
        super(PepperTopTactileSensor, self).__init__(*args, **kwargs)

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
        return PepperTactileSensorMessage

    def onTouchChanged(self, value):
        self.output_message(PepperTactileSensorMessage(value))

    def start(self):
        super(PepperTopTactileSensor, self).start()

        self.touch = self.memory_service.subscriber('MiddleTactilTouched')
        id = self.touch.signal.connect(self.onTouchChanged)
        self.ids.append(id)

    def stop(self, *args):
        for id in self.ids:
            self.touch.signal.disconnect(id)
        super(PepperTopTactileSensor, self).stop()


class PepperTopTactile(SICConnector):
    component_class = PepperTopTactileSensor


if __name__ == "__main__":
    SICComponentManager([PepperTopTactileSensor])
