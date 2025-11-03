from sic_framework import SICComponentManager, SICMessage, utils
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
        For offline content, consider using local HTML files or data URIs.
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
        
        :returns: List containing UrlMessage type.
        :rtype: list
        """
        return [UrlMessage]

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
        Handle incoming URL display request.
        
        Displays the requested URL on Pepper's tablet using the ALTabletService.
        
        :param UrlMessage message: Message containing the URL to display.
        """
        self.tablet_service.showWebview(message.url)

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