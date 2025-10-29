from sic_framework import (
    SICActuator,
    SICComponentManager,
    SICConfMessage,
    SICMessage,
    SICRequest,
    utils,
)
from sic_framework.core.connector import SICConnector

if utils.PYTHON_VERSION_IS_2:
    import qi


class NaoLEDRequest(SICRequest):
    """
    Request to turn one or more LEDs on or off.

    :param str name: RGB LED or group name, see http://doc.aldebaran.com/2-5/naoqi/sensors/alleds.html.
    :param bool value: True to turn on, False to turn off.
    """

    def __init__(self, name, value):
        super(NaoLEDRequest, self).__init__()
        self.name = name
        self.value = value


class NaoSetIntensityRequest(SICRequest):
    """
    Request to change the intensity of one or more LEDs.

    :param str name: RGB LED or group name, see http://doc.aldebaran.com/2-5/naoqi/sensors/alleds.html.
    :param float intensity: Intensity value in [0, 1].
    """

    def __init__(self, name, intensity):
        super(NaoSetIntensityRequest, self).__init__()
        self.name = name
        self.intensity = intensity


class NaoGetIntensityRequest(SICRequest):
    """
    Request to retrieve the intensity of an LED or LED group.

    :param str name: RGB LED or group name, see http://doc.aldebaran.com/2-5/naoqi/sensors/alleds.html.
    """

    def __init__(self, name):
        super(NaoGetIntensityRequest, self).__init__()
        self.name = name


class NaoGetIntensityReply(SICMessage):
    """
    Message containing the LED intensity value.

    :param float value: Intensity value in [0, 1].
    """

    def __init__(self, value):
        super(NaoGetIntensityReply, self).__init__()
        self.value = value


class NaoFadeRGBRequest(SICRequest):
    """
    Request to fade one or more LEDs to a target RGB color.

    :param str name: RGB LED or group name, see http://doc.aldebaran.com/2-5/naoqi/sensors/alleds.html.
    :param float r: Red channel intensity in [0, 1].
    :param float g: Green channel intensity in [0, 1].
    :param float b: Blue channel intensity in [0, 1].
    :param float duration: Duration in seconds for the fade (default = 0 for instant change).
    """

    def __init__(self, name, r, g, b, duration=0.0):
        super(NaoFadeRGBRequest, self).__init__()
        self.name = name
        self.r = r
        self.g = g
        self.b = b
        self.duration = duration


class NaoFadeListRGBRequest(SICRequest):
    """
    Request to cycle LED colors through a list of RGB values over time.

    :param str name: RGB LED or group name, see http://doc.aldebaran.com/2-5/naoqi/sensors/alleds.html.
    :param list[int] rgbs: List of RGB values in hexadecimal format [0x00RRGGBB, ...].
    :param list[float] durations: List of durations (in seconds) corresponding to each RGB value.
    """

    def __init__(self, name, rgbs, durations):
        super(NaoFadeListRGBRequest, self).__init__()
        self.name = name
        self.rgbs = rgbs
        self.durations = durations


class NaoBasicAwarenessRequest(SICRequest):
    """
    Request to enable or disable basic awareness and configure its parameters.

    :param bool value: True to enable, False to disable basic awareness.
    :param list[tuple[str, bool]] stimulus_detection: Optional list of (stimulus_name, enable) tuples for stimuli types, see http://doc.aldebaran.com/2-5/naoqi/interaction/autonomousabilities/albasicawareness.html#albasicawareness-stimuli-types.
    :param str engagement_mode: Engagement mode, see http://doc.aldebaran.com/2-5/naoqi/interaction/autonomousabilities/albasicawareness.html#albasicawareness-engagement-modes.
    :param str tracking_mode: Tracking mode, see http://doc.aldebaran.com/2-5/naoqi/interaction/autonomousabilities/albasicawareness.html#albasicawareness-tracking-modes.
    """

    def __init__(self, value, stimulus_detection=None, engagement_mode=None, tracking_mode=None):
        super(NaoBasicAwarenessRequest, self).__init__()
        self.value = value
        self.stimulus_detection = stimulus_detection if stimulus_detection else []
        self.engagement_mode = engagement_mode
        self.tracking_mode = tracking_mode


class NaoqiLEDsActuator(SICActuator):
    """
    Actuator for controlling LEDs through the NAOqi ALLeds service.

    Supports requests for turning LEDs on/off, changing colors, and adjusting intensity levels.

    :ivar qi.Session session: Connection to the local NAOqi framework.
    :ivar Any leds: Handle to the ALLeds service.
    """

    def __init__(self, *args, **kwargs):
        super(NaoqiLEDsActuator, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")

        # Connect to AL proxies
        self.leds = self.session.service("ALLeds")

    @staticmethod
    def get_conf():
        return SICConfMessage()

    @staticmethod
    def get_inputs():
        return [
            NaoFadeRGBRequest,
            NaoFadeListRGBRequest,
            NaoLEDRequest,
            NaoSetIntensityRequest,
            NaoGetIntensityRequest,
        ]

    @staticmethod
    def get_output():
        return SICMessage

    def execute(self, message):
        """
        Execute a LED control request.

        :param SICRequest message: LED-related request to process.
        :returns: Reply message (e.g., NaoGetIntensityReply or generic SICMessage).
        :rtype: SICMessage
        """
        if message == NaoFadeRGBRequest:
            self.leds.fadeRGB(
                message.name, message.r, message.g, message.b, message.duration
            )
        elif message == NaoFadeListRGBRequest:
            self.leds.fadeListRGB(message.name, message.rgbs, message.durations)
        elif message == NaoLEDRequest:
            if message.value:
                self.leds.on(message.name)
            else:
                self.leds.off(message.name)
        elif message == NaoSetIntensityRequest:
            self.leds.setIntensity(message.name, message.intensity)
        elif message == NaoGetIntensityRequest:
            return NaoGetIntensityReply(self.leds.getIntensity(message.name))
        return SICMessage()

    def stop(self, *args):
        """
        Stop the LEDs actuator, close the NAOqi session, and release resources.

        """
        self.session.close()
        self._stopped.set()
        super(NaoqiLEDsActuator, self).stop()


class NaoqiLEDs(SICConnector):
    component_class = NaoqiLEDsActuator


if __name__ == "__main__":
    SICComponentManager([NaoqiLEDs])
