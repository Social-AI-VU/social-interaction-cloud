import asyncio
from time import sleep

from sic_framework import SICComponentManager, SICService, utils
from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage, SICRequest
from sic_framework.devices.common_mini.mini_connector import MiniConnector

from mini.apis.api_action import PlayAction, PlayActionResponse


class MiniActionRequest(SICRequest):
    """
    Perform Mini actions based on their action name.
    TODO: add more documentation
    """

    def __init__(self, name):
        super(MiniActionRequest, self).__init__()
        self.name = name


class MiniConnectRequest(SICRequest):
    """
    Connect to mini api to be able to run the pre-installed actions, behaviors, and expressions.
    :param mini_id: the last 5 digits of mini's serial number.
    TODO: connecting is not working, probably because of a conflict with android apps.
    """

    def __init__(self, mini_id):
        super(MiniConnectRequest, self).__init__()
        self.mini_id = mini_id


class MiniDisconnectRequest(SICRequest):
    """
    Disconnect from mini api.
    """

    def __init__(self):
        super(MiniDisconnectRequest, self).__init__()


class MiniAnimationActuator(SICActuator):
    COMPONENT_STARTUP_TIMEOUT = 5

    def __init__(self, *args, **kwargs):
        SICActuator.__init__(self, *args, **kwargs)
        self.alphamini = None

    @staticmethod
    def get_inputs():
        return [
            MiniActionRequest,
            MiniConnectRequest,
            MiniDisconnectRequest,
        ]

    @staticmethod
    def get_output():
        return SICMessage

    def execute(self, request):
        if request == MiniActionRequest:
            asyncio.run(self.action(request))
        elif request == MiniConnectRequest:
            self.connect(request)
        return SICMessage()

    async def action(self, request):
        block: PlayAction = PlayAction(action_name=request.name)
        # response: PlayActionResponse
        (resultType, response) = await block.execute()

        self.logger.info(f'Mini action {request.name} was {resultType}:{response}')

    def connect(self, request):
        self.logger.info(f'Connecting to alphamini python API for {request.mini_id}')
        self.alphamini = MiniConnector(request.mini_id)
        self.alphamini.connect()
        sleep(1)
        self.logger.info(f'Connected')

    def disconnect(self):
        if self.alphamini:
            self.alphamini.disconnect()
            self.logger.info(f'Disconnecting from alphamini python API')

class MiniAnimation(SICConnector):
    component_class = MiniAnimationActuator


if __name__ == "__main__":
    SICComponentManager([MiniAnimationActuator])
