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
from sic_framework.core.utils import is_sic_instance
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

    def _build_messages(
        self,
        user_messages,
        context_messages=None,
        system_message=None,
        role_messages=None,
    ):
        """
        Construct the OpenAI chat messages list from the provided inputs.
        """
        messages = []

        if role_messages:
            for msg in role_messages:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    messages.append(msg)

        if self.params.system_message != "":
            messages.append({"role": "system", "content": self.params.system_message})
        if system_message:
            messages.append({"role": "system", "content": system_message})

        if context_messages:
            for context_message in context_messages:
                if isinstance(context_message, dict) and "role" in context_message and "content" in context_message:
                    messages.append(context_message)
                else:
                    messages.append({"role": "user", "content": context_message})

        if user_messages is not None and user_messages != "":
            messages.append({"role": "user", "content": user_messages})

        return messages

    def get_openai_response(
        self,
        user_messages,
        context_messages=None,
        system_message=None,
        model=None,
        temp=None,
        max_tokens=None,
        response_format=None,
        role_messages=None,
    ):
        """
        Generate a response from OpenAI GPT models.
        
        This method constructs the message payload and sends it to the OpenAI API to generate
        a response. It handles system messages, conversation context, and parameter overrides.
        """
        messages = self._build_messages(
            user_messages=user_messages,
            context_messages=context_messages,
            system_message=system_message,
            role_messages=role_messages,
        )

        # Prefer per-request overrides, then fall back to configuration default
        effective_response_format = (
            response_format if response_format is not None else getattr(self.params, "response_format", None)
        )

        kwargs = {
            "model": model if model else self.params.model,
            "messages": messages,
            "temperature": temp if temp else self.params.temp,
            "max_tokens": max_tokens if max_tokens else self.params.max_tokens,
        }
        if effective_response_format is not None:
            kwargs["response_format"] = effective_response_format

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        num_tokens = response.usage.total_tokens if response.usage else 0
        output = GPTResponse(content, num_tokens)
        output.usage_data = getattr(response, "usage", None)
        output.raw_response = response
        return output

    def on_message(self, message):
        """
        Handle input messages.

        :param message: The message to handle
        :type message: SICMessage
        """

        self.logger.debug("Received message: %s", message)

        # Use is_sic_instance because messages are deserialized across processes
        if not is_sic_instance(message, GPTRequest):
            return

        # For GPTRequest messages, delegate directly to the request handler so that
        # both request() and send_message() share the same streaming / non-streaming logic.
        # Any streamed chunks and the final response are handled inside on_request.
        self.on_request(message)

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
        self.logger.debug("Received request: %s", request)
        # Use is_sic_instance for compatibility with pickled messages
        if not is_sic_instance(request, GPTRequest):
            self.logger.error("Invalid request type: %s", type(request))
            return SICMessage("Invalid request type: %s", type(request))

        # If streaming is requested, emit intermediate GPTResponse chunks over the
        # output channel and return the final GPTResponse so request() callers get
        # a complete reply while subscribers see real-time tokens.
        if getattr(request, "stream", False):
            messages = self._build_messages(
                user_messages=request.prompt,
                context_messages=request.context_messages,
                system_message=request.system_message,
                role_messages=getattr(request, "role_messages", None),
            )

            # Prefer per-request overrides, then fall back to configuration default
            effective_response_format = getattr(
                request, "response_format", None
            ) or getattr(self.params, "response_format", None)

            stream_kwargs = {
                "model": request.model if request.model else self.params.model,
                "messages": messages,
                "temperature": request.temp if request.temp else self.params.temp,
                "max_tokens": request.max_tokens if request.max_tokens else self.params.max_tokens,
                "stream": True,
            }
            if effective_response_format is not None:
                stream_kwargs["response_format"] = effective_response_format

            stream = self.client.chat.completions.create(**stream_kwargs)

            full_content = ""
            last_usage = None
            for chunk in stream:
                choice = chunk.choices[0]
                delta_content = getattr(choice.delta, "content", None)
                if delta_content:
                    full_content += delta_content
                    resp_chunk = GPTResponse(delta_content, 0)
                    resp_chunk.is_stream_chunk = True
                    resp_chunk.full_response = full_content
                    resp_chunk.finish_reason = getattr(choice, "finish_reason", None)
                    resp_chunk.usage_data = getattr(chunk, "usage", None)
                    # Send intermediate chunk over the output channel
                    self.output_message(resp_chunk)
                    last_usage = getattr(chunk, "usage", None)

            # Build and return the final response to the requester
            if full_content:
                final_tokens = getattr(last_usage, "total_tokens", 0) if last_usage else 0
                final_resp = GPTResponse(full_content, final_tokens)
                final_resp.is_stream_chunk = False
                final_resp.full_response = full_content
                final_resp.usage_data = last_usage
                # Also emit the final response on the output channel for symmetry
                self.output_message(final_resp)
                return final_resp

            # If no content was produced, fall back to an empty response
            return GPTResponse("", 0)

        # Non-streaming request: just run a single completion and return it
        self.logger.debug("Getting OpenAI response for request: %s", request)
        output = self.get_openai_response(
            request.prompt,
            context_messages=request.context_messages,
            system_message=request.system_message,
            model=request.model,
            temp=request.temp,
            max_tokens=request.max_tokens,
            response_format=getattr(request, "response_format", None),
            role_messages=getattr(request, "role_messages", None),
        )
        return output

    def stop(self, *args):
        """
        Stop the GPTComponent.
        """
        super(GPTComponent, self).stop(*args)

    def _cleanup(self):
        try:
            client = getattr(self, "client", None)
            if client is not None and hasattr(client, "close"):
                client.close()
        except Exception:
            pass


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
