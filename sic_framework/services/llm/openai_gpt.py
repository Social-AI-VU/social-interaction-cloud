"""
OpenAI GPT service.

This service provides integration with OpenAI's GPT models for natural language processing tasks.
It allows sending text prompts to GPT models and receiving generated responses through the SIC framework.
The service supports various GPT models, with configurable parameters for temperature, token limits, and system messages.
"""

from openai import OpenAI
from sic_framework import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICMessage, SICRequest
from sic_framework.core.service_python2 import SICService
from sic_framework.services.llm import GPTRequest, GPTResponse, GPTConf, LLMRequest


class GPTComponent(SICService):
    """
    OpenAI GPT service component for natural language generation.

    This service component provides integration with OpenAI's GPT models through the SIC framework.
    It handles authentication, request processing, and response formatting for GPT interactions.
    The service supports various GPT models and allows for flexible configuration of model parameters.

    The component maintains a persistent OpenAI client connection and processes GPTRequest messages
    to generate natural language responses using the specified GPT model.
    """

    def __init__(self, *args, **kwargs):
        super(GPTComponent, self).__init__(*args, **kwargs)
        self.client = OpenAI(api_key=self.params.api_key)

    @staticmethod
    def get_inputs():
        return [GPTRequest]

    @staticmethod
    def get_output():
        return GPTResponse

    # This function is optional
    @staticmethod
    def get_conf():
        return GPTConf()

    # @backoff.on_exception(backoff.expo, openai.error.RateLimitError)
    def get_openai_response(
        self,
        user_messages,
        context_messages=None,
        system_message=None,
        model=None,
        temp=None,
        max_tokens=None,
    ):
        """
        Generate a response from OpenAI GPT models.

        This method constructs the message payload and sends it to the OpenAI API to generate
        a response. It handles system messages, conversation context, and parameter overrides.

        :param user_messages: The main user message/prompt to send to the GPT model
        :type user_messages: str
        :param context_messages: Optional list of previous messages for conversation context
        :type context_messages: list[str] or None
        :param model: Optional model override (uses service default if None)
        :type model: str or None
        :param temp: Optional temperature override (uses service default if None)
        :type temp: float or None
        :param max_tokens: Optional max tokens override (uses service default if None)
        :type max_tokens: int or None
        :return: GPTResponse containing the generated text and token usage information
        :rtype: GPTResponse
        """
        messages = []
        if self.params.system_message != "":
            messages.append({"role": "system", "content": self.params.system_message})
        if system_message:
            messages.append({"role": "system", "content": system_message})
        if context_messages:
            for context_message in context_messages:
                messages.append({"role": "user", "content": context_message})

        messages.append({"role": "user", "content": user_messages})

        response = self.client.chat.completions.create(
            model=model if model else self.params.model,
            messages=messages,
            temperature=temp if temp else self.params.temp,
            max_tokens=max_tokens if max_tokens else self.params.max_tokens,
        )
        content = response.choices[0].message.content
        num_tokens = response.usage.total_tokens
        return GPTResponse(content, num_tokens)

    def on_message(self, message):
        """
        Handle input messages.

        The GPTComponent currently doesn't handle direct messages and this method
        is a placeholder for future implementation. For now, all interactions
        should use the request-response pattern via on_request method.

        :param message: The message to handle
        :type message: SICMessage
        """
        pass
        # TODO
        # output = self.get_openai_response(message.text)
        # self.output_message(output)

    def on_request(self, request):
        """
        Handle requests for GPT text generation.

        This method processes GPTRequest messages and generates responses using the OpenAI GPT API.
        It validates the request type and delegates to the get_openai_response method for actual
        text generation. Returns a GPTResponse containing the generated text.

        :param request: The request to handle, should be a GPTRequest instance
        :type request: SICRequest
        :return: GPTResponse with generated text and token usage, or error message for invalid requests
        :rtype: GPTResponse or SICMessage
        """
        if not isinstance(request, GPTRequest):
            self.logger.error("Invalid request type: %s", type(request))
            return SICMessage("Invalid request type: %s", type(request))
        else:
            output = self.get_openai_response(
                request.prompt,
                context_messages=request.context_messages,
                system_message=request.system_message,
                model=request.model,
                temp=request.temp,
                max_tokens=request.max_tokens,
            )
            return output

    def stop(self):
        """
        Stop the GPTComponent.
        """
        self._stopped.set()
        super(GPTComponent, self).stop()


class GPT(SICConnector):
    """
    Connector for the SIC OpenAI GPT Component.
    """
    component_class = GPTComponent


def main():
    """
    Run a ComponentManager that can start the OpenAI GPT Component, called by 'run-gpt'
    """
    SICComponentManager([GPTComponent], name="GPT")


if __name__ == "__main__":
    main()
