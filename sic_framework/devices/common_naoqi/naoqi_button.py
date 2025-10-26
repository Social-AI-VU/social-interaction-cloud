from sic_framework import SICComponentManager, SICConfMessage, SICMessage, utils
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector

if utils.PYTHON_VERSION_IS_2:
    import qi


class NaoqiButtonMessage(SICMessage):
    def __init__(self, value):
        """
        Initialize a message carrying button/touch values.

        For more information, see: http://doc.aldebaran.com/2-4/naoqi/sensors/altouch.html

        Examples:
            [[Head/Touch/Middle, True], [ChestBoard/Button, True]]
            [[Head/Touch/Middle, False]]

        :param list[list[Any, bool]] value: List of button/touch name-value pairs.
        """
        super(NaoqiButtonMessage, self).__init__()
        self.value = value


class NaoqiButtonSensor(SICComponent):
    """
    NaoqiButtonSensor is a sensor that reads the robot's physical button and touch values from the ALMemory module.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the button sensor by connecting to ALMemory and subscribing to touch signals.

        :param Any args: Positional arguments passed to the SICComponent.
        :param Any kwargs: Keyword arguments passed to the SICComponent.
        """
        super(NaoqiButtonSensor, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        # Connect to AL proxies
        self.memory_service = self.session.service("ALMemory")

        self.ids = []

    @staticmethod
    def get_conf():
        """
        Return the default configuration for this sensor.

        :returns: Default configuration message.
        :rtype: SICConfMessage
        """
        return SICConfMessage()

    @staticmethod
    def get_inputs():
        """
        Return the list of input message types accepted by this component.

        :returns: Empty list since this is a sensor-only component.
        :rtype: list
        """
        return []

    @staticmethod
    def get_output():
        """
        Return the output message type produced by this component.

        :returns: The message class used for touch/button events.
        :rtype: type
        """
        return NaoqiButtonMessage

    def onTouchChanged(self, value):
        """
        Callback triggered when a touch or button state changes.

        :param list[list[str, bool]] value: List of name-value pairs representing button/touch changes.
        """
        self.output_message(NaoqiButtonMessage(value))

    def start(self):
        """
        Start the sensor by subscribing to the 'TouchChanged' ALMemory event.

        :returns: None
        :rtype: None
        """
        super(NaoqiButtonSensor, self).start()

        self.touch = self.memory_service.subscriber("TouchChanged")
        id = self.touch.signal.connect(self.onTouchChanged)
        self.ids.append(id)

    def stop(self, *args):
        """
        Stop the touch sensor by disconnecting signals and closing the session.

        :returns: None
        :rtype: None
        """
        for id in self.ids:
            self.touch.signal.disconnect(id)
        self.session.close()
        self._stopped.set()
        super(NaoqiButtonSensor, self).stop()


class NaoqiButton(SICConnector):
    component_class = NaoqiButtonSensor


if __name__ == "__main__":
    SICComponentManager([NaoqiButtonSensor])
