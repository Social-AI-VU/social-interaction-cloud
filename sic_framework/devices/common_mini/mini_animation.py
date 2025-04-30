import asyncio

from sic_framework import SICComponentManager, SICService, utils
from sic_framework.core.actuator_python2 import SICActuator
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage, SICRequest
from sic_framework.devices.common_mini.mini_connector import MiniConnector
import mini.mini_sdk as MiniSdk
from mini.dns.dns_browser import WiFiDevice
from mini.apis.api_expression import PlayExpression, PlayExpressionResponse


from mini.apis.api_action import PlayAction, PlayActionResponse


class MiniActionRequest(SICRequest):
    """
    Perform Mini actions based on their action name.
    TODO: add more documentation
    """

    def __init__(self, name, movement="action", mini_id="00199"):
        super(MiniActionRequest, self).__init__()
        self.mini_id = mini_id
        self.name = name
        asyncio.run(self.main(movement))

    async def main(self, movement):
        device: WiFiDevice = await self.test_get_device_by_name()
        if device:
            await MiniSdk.connect(device)
            await self._run_sdk_action(movement)
            await MiniSdk.quit_program() 
            await MiniSdk.release() 

    async def test_get_device_by_name(self):
        result: WiFiDevice = await MiniSdk.get_device_by_name(self.mini_id, 10)
        return result

    async def _run_sdk_action(self, movement):
        if movement != "expression":
            sdk_action_block: PlayAction = PlayAction(action_name=self.name)
            await sdk_action_block.execute()
        else:
            sdk_expression_block: PlayExpression = PlayExpression(express_name=self.name)
            await sdk_expression_block.execute()



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
