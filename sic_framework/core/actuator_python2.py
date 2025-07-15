"""
actuator_python2.py

This module contains the SICActuator class.
"""
from abc import abstractmethod

from sic_framework.core.component_python2 import SICComponent

from .message_python2 import SICMessage


class SICActuator(SICComponent):
    """
    Abstract class for Actuators that provide physical actions for the Social Interaction Cloud.

    Actuators must implement the execute method individually.
    """

    def on_request(self, request):
        """
        Handle a request from the client. Calls the execute method.

        :param request: input messages
        :type request: SICRequest
        :rtype: SICMessage
        """
        reply = self.execute(request)
        return reply

    @abstractmethod
    def execute(self, request):
        """
        Main function of the Actuator. Must return a SICMessage as a reply to the user.
        
        Must be implemented by the subclass.
        
        :param request: input messages
        :type request: SICRequest
        :rtype: SICMessage
        """
        return NotImplementedError("You need to define device execution.")