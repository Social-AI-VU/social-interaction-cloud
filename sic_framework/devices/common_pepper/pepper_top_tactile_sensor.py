from sic_framework import SICComponentManager, SICConfMessage, SICMessage, utils
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector

if utils.PYTHON_VERSION_IS_2:
    import qi


class PepperTactileSensorMessage(SICMessage):
    """
    Message containing tactile sensor state.
    
    :ivar int value: Touch state - 1 when touched, 0 when released.
    
    See: http://doc.aldebaran.com/2-5/naoqi/sensors/altouch-api.html#MiddleTactilTouched
    """
    
    def __init__(self, value):
        """
        Initialize tactile sensor message.
        
        :param int value: Touch state (1 = touched, 0 = released).
        """
        super(PepperTactileSensorMessage, self).__init__()
        self.value = value


class PepperTopTactileSensor(SICComponent):
    """
    Sensor component for Pepper's top head tactile sensor.
    
    Monitors the middle tactile button on top of Pepper's head and emits events
    when the sensor is touched or released. This is the primary touch-sensitive
    area on Pepper's head, located at the center-top.
    
    This sensor subscribes to NAOqi's ALMemory ``MiddleTactilTouched`` event and
    publishes :class:`PepperTactileSensorMessage` instances through the SIC framework.
    
    Example usage::
    
        def on_head_touch(msg):
            if msg.value == 1:
                print("Head touched!")
            else:
                print("Touch released!")
        
        pepper.tactile_sensor.register_callback(on_head_touch)
    
    .. note::
        This sensor monitors the physical touch-sensitive area on Pepper's head,
        not a clickable button. Light touch is sufficient to trigger the event.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the tactile sensor.
        
        Establishes connection to NAOqi session and ALMemory service.
        
        :param args: Variable length argument list passed to parent.
        :param kwargs: Arbitrary keyword arguments passed to parent.
        """
        super(PepperTopTactileSensor, self).__init__(*args, **kwargs)

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
        
        :returns: PepperTactileSensorMessage class.
        :rtype: type
        """
        return PepperTactileSensorMessage

    def onTouchChanged(self, value):
        """
        Callback invoked when tactile sensor state changes.
        
        :param int value: New touch state (1 = touched, 0 = released).
        """
        self.output_message(PepperTactileSensorMessage(value))

    def start(self):
        """
        Start the sensor and subscribe to touch events.
        
        Connects to the NAOqi ``MiddleTactilTouched`` event and begins emitting
        messages when the tactile sensor state changes.
        """
        super(PepperTopTactileSensor, self).start()

        self.touch = self.memory_service.subscriber('MiddleTactilTouched')
        id = self.touch.signal.connect(self.onTouchChanged)
        self.ids.append(id)

    def stop(self, *args):
        """
        Stop the sensor and clean up resources.
        
        Disconnects from NAOqi events and closes the session.
        
        :param args: Variable length argument list (unused).
        """
        for id in self.ids:
            self.touch.signal.disconnect(id)
        self.session.close()
        self._stopped.set()
        super(PepperTopTactileSensor, self).stop()


class PepperTopTactile(SICConnector):
    """
    Connector for accessing Pepper's top tactile sensor.
    
    Provides a high-level interface to the :class:`PepperTopTactileSensor` component.
    Access this through the Pepper device's ``tactile_sensor`` property.
    """
    component_class = PepperTopTactileSensor


if __name__ == "__main__":
    SICComponentManager([PepperTopTactileSensor])