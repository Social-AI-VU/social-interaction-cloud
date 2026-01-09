"""
Nebula service.

This service provides integration with VU / Network Institute's Nebula platform giving access to a number of genAI models.
It allows sending text prompts to LLM models and receiving generated responses through the SIC framework.
"""

from openai import OpenAI
from sic_framework import SICComponentManager
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICMessage, SICRequest
from sic_framework.core.service_python2 import SICService
from sic_framework.core.utils import is_sic_instance
from sic_framework.services.llm import LLMRequest, LLMResponse, LLMConf, AvailableModelsRequest
from sic_framework.services.llm.llm_messages import AvailableModels


class NebulaComponent(SICService):
    """
    Nebula LLM service component for LLM requests.

    This service component provides integration with Nebula's LLM models through the SIC framework.
    It handles authentication, request processing, and response formatting for LLM interactions.
    The service supports various LLM models and allows for flexible configuration of model parameters.

    The component maintains a persistent Nebula client connection and processes LLMRequest messages
    to LLM responses using the specified LLM model.
    """

    def __init__(self, *args, **kwargs):
        super(NebulaComponent, self).__init__(*args, **kwargs)
        self.client = OpenAI(base_url='https://nebula.cs.vu.nl/api/', api_key=self.params.api_key)

    @staticmethod
    def get_inputs():
        return [LLMRequest]

    @staticmethod
    def get_output():
        return LLMResponse

    # This function is optional
    @staticmethod
    def get_conf():
        return LLMConf()

    # @backoff.on_exception(backoff.expo, openai.error.RateLimitError)
    def get_nebula_response(
        self,
        prompt,
        context_messages=None,
        system_message=None,
        model=None,
        temp=None,
        max_tokens=None
    ):
        """
        Generate a response from OpenAI GPT models.

        This method constructs the message payload and sends it to the OpenAI API to generate
        a response. It handles system messages, conversation context, and parameter overrides.

        :param prompt: The main user message/prompt to send to the GPT model
        :type prompt: str
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

        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=model if model else self.params.model,
            messages=messages,
            temperature=temp if temp else self.params.temp,
            max_tokens=max_tokens if max_tokens else self.params.max_tokens,
        )
        content = response.choices[0].message.content
        num_tokens = response.usage.total_tokens
        if self.params.return_usage_data:
            return LLMResponse(content, num_tokens, response.usage)
        return LLMResponse(content, num_tokens)


    def on_message(self, message):
        """
        Handle input messages.

        The NebulaComponent currently doesn't handle direct messages and this method
        is a placeholder for future implementation. For now, all interactions
        should use the request-response pattern via on_request method.

        :param message: The message to handle
        :type message: SICMessage
        """
        pass
        # TODO
        # output = self.get_openai_response(message.text)
        # self.output_message(output)

    def on_request(self, request: SICRequest):
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
        if is_sic_instance(request, LLMRequest):
            return self.get_nebula_response(
                request.prompt,
                context_messages=request.context_messages,
                system_message=request.system_message,
                model=request.model,
                temp=request.temp,
                max_tokens=request.max_tokens
            )
        elif is_sic_instance(request, AvailableModelsRequest):
            return AvailableModels([model.id for model in self.client.models.list().data])
        else:
            self.logger.error("Invalid request type: %s", type(request))
            return SICMessage("Invalid request type: %s", type(request))

    def stop(self):
        """
        Stop the NebulaComponent..
        """
        self._stopped.set()
        super(NebulaComponent, self).stop()


class Nebula(SICConnector):
    """
    Connector for the SIC Nebula Component.
    """
    component_class = NebulaComponent


def main():
    """
    Run a ComponentManager that can start the Nebula Component, called by 'run-nebula'
    """
    SICComponentManager([NebulaComponent], name="Nebula")


if __name__ == "__main__":
    main()
