from sic_framework import SICComponentManager, SICConfMessage, SICMessage, utils
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector

if utils.PYTHON_VERSION_IS_2:
    import qi


class PepperRightBumperMessage(SICMessage):
    """
    Message containing right bumper state.
    
    :ivar int value: Bumper state - 1 when pressed, 0 when released.
    """
    
    def __init__(self, value):
        """
        Initialize right bumper message.
        
        :param int value: Bumper state (1 = pressed, 0 = released).
        """
        super(PepperRightBumperMessage, self).__init__()
        self.value = value


class PepperRightBumperSensor(SICComponent):
    """
    Sensor component for Pepper's right bumper.
    
    Monitors the right bumper sensor on Pepper robot and emits events when the
    bumper is pressed or released. The bumper is located on the right side of
    Pepper's base platform.
    
    This sensor subscribes to NAOqi's ALMemory ``RightBumperPressed`` event and
    publishes :class:`PepperRightBumperMessage` instances through the SIC framework.
    
    Example usage::
    
        def on_right_bumper(msg):
            if msg.value == 1:
                print("Right bumper pressed!")
            else:
                print("Right bumper released!")
        
        pepper.right_bumper.register_callback(on_right_bumper)
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the right bumper sensor.
        
        Establishes connection to NAOqi session and ALMemory service.
        
        :param args: Variable length argument list passed to parent.
        :param kwargs: Arbitrary keyword arguments passed to parent.
        """
        super(PepperRightBumperSensor, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        # Connect to ALMemory service for sensor events
        self.memory_service = self.session.service("ALMemory")

        # Track signal connection IDs for cleanup
        self.ids = []

    @staticmethod
    def get_conf():
        """
        Get default configuration for this sensor.
        
        :returns: Default (empty) configuration message.
        :rtype: SICConfMessage
        """
        return SICConfMessage()

    @staticmethod
    def get_inputs():
        """
        Get list of input message types this sensor accepts.
        
        :returns: Empty list (this sensor does not accept input messages).
        :rtype: list
        """
        return []

    @staticmethod
    def get_output():
        """
        Get the output message type this sensor produces.
        
        :returns: PepperRightBumperMessage class.
        :rtype: type
        """
        return PepperRightBumperMessage

    def onBumperChanged(self, value):
        """
        Callback invoked when bumper state changes.
        
        :param int value: New bumper state (1 = pressed, 0 = released).
        """
        self.output_message(PepperRightBumperMessage(value))

    def start(self):
        """
        Start the sensor and subscribe to bumper events.
        
        Connects to the NAOqi ``RightBumperPressed`` event and begins emitting
        messages when the bumper state changes.
        """
        super(PepperRightBumperSensor, self).start()

        self.bumper = self.memory_service.subscriber("RightBumperPressed")
        id = self.bumper.signal.connect(self.onBumperChanged)
        self.ids.append(id)

    def stop(self, *args):
        """
        Stop the sensor and clean up resources.
        
        Disconnects from NAOqi events and closes the session.
        
        :param args: Variable length argument list (unused).
        """
        for id in self.ids:
            self.bumper.signal.disconnect(id)
        self.session.close()
        self._stopped.set()
        super(PepperRightBumperSensor, self).stop()


class PepperRightBumper(SICConnector):
    """
    Connector for accessing Pepper's right bumper sensor.
    
    Provides a high-level interface to the :class:`PepperRightBumperSensor` component.
    Access this through the Pepper device's ``right_bumper`` property.
    """
    component_class = PepperRightBumperSensor


if __name__ == "__main__":
    SICComponentManager([PepperRightBumperSensor]) 