from abc import abstractmethod

from sic_framework.core.component_python2 import SICComponent

from .message_python2 import SICMessage


class SICActuator(SICComponent):
    """
    Actuators are components that do not send messages.
    """
    def __init__(self, *args, **kwargs):
        super(SICActuator, self).__init__(*args, **kwargs)
        self.logger.debug("Setting reservation for {}".format(self.component_id))
        # set_reservation returns the number of keys set, if it is less than 1, then the reservation failed (i.e. already reserved)
        if self._redis.set_reservation(self.component_id, self.client_id) < 1:
            raise Exception("Failed to set reservation for {}, Actuator already in use".format(self.component_id))
        
    @abstractmethod
    def execute(self, request):
        """
        Main function of the device. Must return a SICMessage as a reply to the user.
        :param request: input messages
        :type request: SICRequest
        :rtype: SICMessage
        """
        return NotImplementedError("You need to define device execution.")

    def on_request(self, request):
        reply = self.execute(request)
        return reply
