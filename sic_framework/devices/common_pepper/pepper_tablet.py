from sic_framework import SICComponentManager, SICMessage, utils, SICRequest
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector

if utils.PYTHON_VERSION_IS_2:
    import qi
    from naoqi import ALProxy


class UrlMessage(SICMessage):
    """
    Message containing a URL to display on Pepper's tablet.
    
    :ivar str url: The URL to display in the tablet's webview.
    """
    
    def __init__(self, url):
        """
        Initialize URL message.
        
        :param str url: Web URL to display on the tablet (e.g., "http://example.com").
        """
        super(UrlMessage, self).__init__()
        self.url = url


class WifiConnectRequest(SICRequest):
    """
    Message containing Wi-Fi credentials for Pepper's tablet.

    :ivar str network_name: SSID of the Wi-Fi network to join.
    :ivar str network_password: Password or key used to authenticate.
    :ivar str network_type: Security type (e.g., "open", "wep", "wpa", "wpa2").
    """

    def __init__(self, network_name, network_password, network_type="wpa2"):
        """
        Initialize Wi-Fi connection message.

        :param str network_name: SSID of the Wi-Fi network.
        :param str network_password: Password for the Wi-Fi network.
        :param str network_type: Security type, defaults to "wpa2".
        """
        super(WifiConnectRequest, self).__init__()
        self.network_name = network_name
        self.network_password = network_password or ""
        self.network_type = network_type or "open"


class ClearDisplayMessage(SICMessage):
    """
    Message indicating the tablet display should be cleared.
    """

    def __init__(self):
        super(ClearDisplayMessage, self).__init__()


class DisplayImageMessage(SICMessage):
    """
    Message containing a path to an image on Pepper's tablet to display.
    """

    def __init__(self, image_path):
        """
        Initialize image display message.

        :param str image_path: Path to the image accessible from Pepper's tablet.
        """
        super(DisplayImageMessage, self).__init__()
        self.image_path = image_path


class ShowVideoMessage(SICMessage):
    """
    Message containing a path to a video on Pepper's tablet to play.
    """

    def __init__(self, video_path, start_time=0.0):
        """
        Initialize video display message.

        :param str video_path: Path to the video accessible from Pepper's tablet.
        :param float start_time: Optional start time in seconds.
        """
        super(ShowVideoMessage, self).__init__()
        self.video_path = video_path
        self.start_time = start_time or 0.0


class NaoqiTabletComponent(SICComponent):
    """
    Component for controlling Pepper's tablet display.
    
    Provides access to Pepper's built-in tablet screen through NAOqi's ALTabletService.
    Accepts :class:`UrlMessage` requests to display web content on the tablet.
    
    The tablet can display any web content, including:
    
    - Static HTML pages
    - Interactive web applications
    - Images and videos
    - Custom UI elements
    
    Example usage::
    
        from sic_framework.devices.common_pepper.pepper_tablet import UrlMessage
        
        pepper.tablet_display_url.request(UrlMessage("http://example.com"))
    
    .. note::
        The tablet requires active network connectivity to load external URLs.
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the tablet component.
        
        Establishes connection to NAOqi session and ALTabletService.
        
        :param args: Variable length argument list passed to parent.
        :param kwargs: Arbitrary keyword arguments passed to parent.
        """
        super(NaoqiTabletComponent, self).__init__(*args, **kwargs)

        self.session = qi.Session()
        self.session.connect("tcp://127.0.0.1:9559")
        self.tablet_service = self.session.service("ALTabletService", "127.0.0.1", "9559")

    @staticmethod
    def get_inputs():
        """
        Get list of input message types this component accepts.
        
        :returns: List containing supported message types.
        :rtype: list
        """
        return [UrlMessage, WifiConnectRequest, ClearDisplayMessage, DisplayImageMessage, ShowVideoMessage]

    @staticmethod
    def get_output():
        """
        Get the output message type this component produces.
        
        :returns: SICMessage class (generic acknowledgment).
        :rtype: type
        """
        return SICMessage

    def on_message(self, message):
        """
        Handle incoming tablet request messages.
        
        :param SICMessage message: Message to process.
        """
        self.logger.debug("Received message of type: %s", type(message))
        if isinstance(message, UrlMessage):
            self.show_webview(message.url)
        elif isinstance(message, WifiConnectRequest):
            self.wifi_connect(
                network_name=message.network_name,
                network_password=message.network_password,
                network_type=message.network_type,
            )
        elif isinstance(message, ClearDisplayMessage):
            self.clear_display()
        elif isinstance(message, DisplayImageMessage):
            self.display_image(message.image_path)
        elif isinstance(message, ShowVideoMessage):
            self.show_video(message.video_path, message.start_time)

    def on_request(self, request):
        """
        Handle incoming tablet request messages.
        
        :param SICMessage message: Message to process.
        """
        if isinstance(request, WifiConnectRequest):
            try:
                self.wifi_connect(
                network_name=request.network_name,
                    network_password=request.network_password,
                    network_type=request.network_type,
                )
                return SICMessage()
            except Exception as e:
                raise e

    def show_webview(self, url):
        """
        Show the webview on the tablet.
        
        :param str url: The URL to display on the tablet.
        """
        self.logger.debug("Showing webview: %s", url)
        self.tablet_service.showWebview(url)

    def wifi_connect(self, network_name, network_password, network_type):
        """
        Connect the tablet to the specified Wi-Fi network.

        :param str network_name: SSID of the Wi-Fi network.
        :param str network_password: Password/key for the Wi-Fi network.
        :param str network_type: Security type ("open", "wep", "wpa", "wpa2").
        :raises ValueError: If required parameters are missing or invalid.
        :raises RuntimeError: If the tablet service fails to configure Wi-Fi.
        """
        self.logger.debug("Connecting to Wi-Fi network: %s", network_name)
        self.logger.debug("Network password: %s", network_password)
        self.logger.debug("Network type: %s", network_type)

        self.logger.debug("Network name type: %s", type(network_name))

        # if network_name == "" or not isinstance(network_name, str):
        #     raise ValueError("network_name must be a non-empty string.")

        security_aliases = {
            "": "open",
            "none": "open",
            "open": "open",
            "wep": "wep",
            "wpa": "wpa",
            "wpa2": "wpa2",
        }

        normalized_type = (network_type or "").strip().lower()
        security = security_aliases.get(normalized_type)

        if security is None:
            raise ValueError(
                "Unsupported network_type '{}'. Expected one of: {}.".format(
                    network_type, ", ".join(sorted(security_aliases.keys()))
                )
            )

        key = network_password if network_password is not None else ""

        try:
            # configureWifi(security, ssid, key) returns True on success.
            result = self.tablet_service.configureWifi(security, network_name, key)
        except Exception as exc:
            raise RuntimeError("Failed to configure Wi-Fi: {}".format(exc))

        if not result:
            raise RuntimeError("Tablet failed to connect to Wi-Fi network '{}'.".format(network_name))
        return True

    def clear_display(self):
        """
        Clear the current tablet display.

        Uses ALTabletService.cleanWebview to remove any displayed content.

        :raises RuntimeError: If clearing the display fails.
        """
        try:
            self.tablet_service.hideWebview()
            self.tablet_service.cleanWebview()
        except Exception as exc:
            raise RuntimeError("Failed to clear tablet display: {}".format(exc))

    def display_image(self, image_path):
        """
        Display an image stored on Pepper's tablet.

        :param str image_path: Path or URL to the image.
        :raises ValueError: If the image_path is invalid.
        :raises RuntimeError: If the image cannot be displayed.
        """
        # if not image_path or not isinstance(image_path, str):
        #     raise ValueError("image_path must be a non-empty string.")

        try:
            # showImage can accept either local app resource paths or URLs.
            self.tablet_service.showImage(image_path)
        except Exception as exc:
            raise RuntimeError("Failed to display image '{}': {}".format(image_path, exc))

    def show_video(self, video_path, start_time=0.0):
        """
        Play a video stored on Pepper's tablet.

        :param str video_path: Path or URL to the video.
        :param float start_time: Start time in seconds to begin playback.
        :raises ValueError: If the video_path is invalid.
        :raises RuntimeError: If the video cannot be played.
        """
        # if not video_path or not isinstance(video_path, str):
        #     raise ValueError("video_path must be a non-empty string.")

        if start_time is None:
            start_time = 0.0

        try:
            start_time = float(start_time)
        except (TypeError, ValueError):
            raise ValueError("start_time must be a number representing seconds.")

        try:
            # playVideo expects a URL or app resource path.
            self.tablet_service.playVideo(video_path)

            if start_time > 0:
                milliseconds = int(max(0.0, start_time) * 1000)
                self.tablet_service.pauseVideo()
                self.tablet_service.seekVideo(milliseconds)
                self.tablet_service.resumeVideo()
        except Exception as exc:
            raise RuntimeError("Failed to play video '{}': {}".format(video_path, exc))

    def stop(self, *args):
        """
        Stop the component and clean up resources.
        
        Closes the NAOqi session.
        
        :param args: Variable length argument list (unused).
        """
        self.session.close()
        self._stopped.set()
        super(NaoqiTabletComponent, self).stop()


class NaoqiTablet(SICConnector):
    """
    Connector for accessing Pepper's tablet display.
    
    Provides a high-level interface to the :class:`NaoqiTabletComponent`.
    Access this through the Pepper device's ``tablet_display_url`` property.
    """
    component_class = NaoqiTabletComponent


if __name__ == "__main__":
    SICComponentManager([NaoqiTabletComponent])