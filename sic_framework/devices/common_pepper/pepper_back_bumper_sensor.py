from sic_framework import SICComponentManager, SICConfMessage, SICMessage, utils
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector

if utils.PYTHON_VERSION_IS_2:
    import qi


class PepperBackBumperMessage(SICMessage):
    """
    Message containing back bumper state.
    
    :ivar int value: Bumper state - 1 when pressed, 0 when released.
    """
    
    def __init__(self, value):
        """
        Initialize back bumper message.
        
        :param int value: Bumper state (1 = pressed, 0 = released).
        """
        super(PepperBackBumperMessage, self).__init__()
        self.value = value


class PepperBackBumperSensor(SICComponent):
    """
    Sensor component for Pepper's rear bumper.
    
    Monitors the back bumper sensor on Pepper robot and emits events when the
    bumper is pressed or released. The bumper is located on the back of Pepper's
    base platform.
    
    This sensor subscribes to NAOqi's ALMemory ``BackBumperPressed`` event and
    publishes :class:`PepperBackBumperMessage` instances through the SIC framework.
    
    Example usage::
    
        def on_bumper(msg):
            if msg.value == 1:
                print("Back bumper pressed!")
            else:
                print("Back bumper released!")
        
        pepper.back_bumper.register_callback(on_bumper)
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the back bumper sensor.
        
        Establishes connection to NAOqi session and ALMemory service.
        
        :param args: Variable length argument list passed to parent.
        :param kwargs: Arbitrary keyword arguments passed to parent.
        """
        super(PepperBackBumperSensor, self).__init__(*args, **kwargs)

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
        
        :returns: PepperBackBumperMessage class.
        :rtype: type
        """
        return PepperBackBumperMessage

    def onBumperChanged(self, value):
        """
        Callback invoked when bumper state changes.
        
        :param int value: New bumper state (1 = pressed, 0 = released).
        """
        self.output_message(PepperBackBumperMessage(value))

    def start(self):
        """
        Start the sensor and subscribe to bumper events.
        
        Connects to the NAOqi ``BackBumperPressed`` event and begins emitting
        messages when the bumper state changes.
        """
        super(PepperBackBumperSensor, self).start()

        self.bumper = self.memory_service.subscriber("BackBumperPressed")
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
        super(PepperBackBumperSensor, self).stop()


class PepperBackBumper(SICConnector):
    """
    Connector for accessing Pepper's back bumper sensor.
    
    Provides a high-level interface to the :class:`PepperBackBumperSensor` component.
    Access this through the Pepper device's ``back_bumper`` property.
    """
    component_class = PepperBackBumperSensor


if __name__ == "__main__":
    SICComponentManager([PepperBackBumperSensor])