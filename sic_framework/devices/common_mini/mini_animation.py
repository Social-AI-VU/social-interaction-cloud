import asyncio

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
        self.alphamini = MiniConnector()
        self.alphamini.connect()


class MiniAnimationActuator(SICActuator):
    COMPONENT_STARTUP_TIMEOUT = 5

    def __init__(self, *args, **kwargs):
        SICActuator.__init__(self, *args, **kwargs)

    @staticmethod
    def get_inputs():
        return [
            MiniActionRequest,
        ]

    @staticmethod
    def get_output():
        return SICMessage

    def execute(self, request):
        if request == MiniActionRequest:
            asyncio.run(self.action(request))

        return SICMessage()

    async def action(self, request):
        block: PlayAction = PlayAction(action_name=request.name)
        # response: PlayActionResponse
        (resultType, response) = await block.execute()

        self.logger.info(f'Mini action {request.name} was {resultType}:{response}')


class MiniAnimation(SICConnector):
    component_class = MiniAnimationActuator


if __name__ == "__main__":
    SICComponentManager([MiniAnimationActuator])
