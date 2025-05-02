import asyncio

import mini.mini_sdk as MiniSdk
from mini.apis.api_action import PlayAction
from mini.apis.api_expression import PlayExpression
from mini.dns.dns_browser import WiFiDevice

from sic_framework import SICComponentManager
from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICMessage, SICRequest


class MiniActionRequest(SICRequest):
    """
    Perform Mini actions based on their action name.
    TODO: add more documentation
    """

    def __init__(self, mini_id, name, movement="action"):
        super(MiniActionRequest, self).__init__()
        self.mini_id = mini_id
        self.name = name
        self.movement = movement
        print(f'MiniActionRequest is made with {name}, {movement} for mini with id {mini_id}')


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
        print(f'Received Request: {request}')
        if request == MiniActionRequest:
            print('Executing MiniActionRequest')
            asyncio.run(self.main(request))
            print('Done Executing MiniActionRequest')

        return SICMessage()

    async def main(self, request):
        device: WiFiDevice = await self.test_get_device_by_name(request.mini_id)
        if device:
            await MiniSdk.connect(device)
            await self._run_sdk_action(request.name, request.movement)
            # await MiniSdk.quit_program()
            await MiniSdk.release()

    async def test_get_device_by_name(self, mini_id):
        result: WiFiDevice = await MiniSdk.get_device_by_name(mini_id, 10)
        return result

    async def _run_sdk_action(self, name, movement):
        if movement != "expression":
            sdk_action_block: PlayAction = PlayAction(action_name=name)
            await sdk_action_block.execute()
        else:
            sdk_expression_block: PlayExpression = PlayExpression(express_name=name)
            await sdk_expression_block.execute()

    async def action(self, request):
        block: PlayAction = PlayAction(action_name=request.name)
        # response: PlayActionResponse
        (resultType, response) = await block.execute()

        self.logger.info(f'Mini action {request.name} was {resultType}:{response}')


class MiniAnimation(SICConnector):
    component_class = MiniAnimationActuator


if __name__ == "__main__":
    SICComponentManager([MiniAnimationActuator])
