from sic_framework import SICComponentManager, SICMessage, utils, SICRequest
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector

if utils.PYTHON_VERSION_IS_2:
    import qi
    from naoqi import ALProxy

import time

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


class NaoqiTabletComponent(SICComponent):
    """
    Component for controlling Pepper's tablet display.
    
    Provides access to Pepper's built-in tablet screen through NAOqi's ALTabletService.
    Accepts :class:`UrlMessage` requests to display web content on the tablet.

    The tablet may need to be configured with a Wi-Fi network before it can be used.

    For information on the available methods (not implemented yet), please refer to the NAOqi ALTabletService API documentation:
    http://doc.aldebaran.com/2-5/naoqi/core/altabletservice-api.html
        
    Example usage::
    
        from sic_framework.devices.common_pepper.pepper_tablet import UrlMessage
        
        pepper.tablet.send_message(UrlMessage("http://example.com"))
    
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
        self.tablet_service = self.session.service("ALTabletService")

    @staticmethod
    def get_inputs():
        """
        Get list of input message types this component accepts.
        
        :returns: List containing supported message types.
        :rtype: list
        """
        return [UrlMessage, WifiConnectRequest, ClearDisplayMessage]

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
        else:
            self.logger.error("Unsupported message type: %s", type(message))

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
        self.logger.debug("Awakening webview before displaying URL.")
        self.tablet_service.showWebview()
        time.sleep(3)
        self.logger.debug("Displaying webview: %s", url)
        self.tablet_service.showWebview(url)

    def wifi_connect(self, network_name, network_password, network_type):
        """
        Connect the tablet to the specified Wi-Fi network.

        :param str network_name: SSID of the Wi-Fi network.
        :param str network_password: Password/key for the Wi-Fi network.
        :param str network_type: Security type ("open", "wep", "wpa", "wpa2").
        :raises RuntimeError: If the tablet service fails to configure Wi-Fi.
        """
        self.logger.debug("Connecting to Wi-Fi network: %s", network_name)
        self.logger.debug("Network password: %s", network_password)
        self.logger.debug("Network type: %s", network_type)

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
    Access this through the Pepper device's ``tablet`` property.
    """
    component_class = NaoqiTabletComponent


if __name__ == "__main__":
    SICComponentManager([NaoqiTabletComponent])