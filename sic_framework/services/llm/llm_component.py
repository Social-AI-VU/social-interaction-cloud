import llm

from sic_framework import SICComponentManager, SICConfMessage
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICMessage, SICRequest


class LlmConf(SICConfMessage):
    """
    Configuration for LLM component
    :param model: Model ID to use (e.g., 'gpt-4', 'orca-mini-3b-gguf2-q4_0')
    :param openai_key: OpenAI API key for OpenAI models
    :param system_prompt: Optional system prompt to use for all requests
    """

    def __init__(
        self, model="orca-mini-3b-gguf2-q4_0", openai_key=None, system_prompt=None
    ):
        super(SICConfMessage, self).__init__()
        self.model = model
        self.openai_key = openai_key
        self.system_prompt = system_prompt


class PromptRequest(SICRequest):
    def __init__(self, prompt, system_prompt=None):
        """
        Request to generate text from a prompt
        :param prompt: The prompt text to send to the model
        :param system_prompt: Optional system prompt to override the default
        """
        super().__init__()
        self.prompt = prompt
        self.system_prompt = system_prompt


class LlmResponse(SICMessage):
    def __init__(self, response):
        super().__init__()
        self.response = response


class LlmComponent(SICComponent):
    """
    Component for interacting with LLM models using the llm library
    """

    def __init__(self, *args, **kwargs):
        super(LlmComponent, self).__init__(*args, **kwargs)
        self.model = llm.get_model(self.params.model)
        # Set OpenAI key if provided
        if self.params.openai_key:
            self.model.key = self.params.openai_key

    @staticmethod
    def get_inputs():
        return [PromptRequest]

    @staticmethod
    def get_output():
        return LlmResponse

    @staticmethod
    def get_conf():
        return LlmConf()

    def on_request(self, request):
        system_prompt = request.system_prompt or self.params.system_prompt

        # Execute the prompt with optional system prompt
        response = self.model.prompt(request.prompt, system=system_prompt)
        print(f"The model used: {self.params.model}")
        print(f"LLM Response: {response.text()}")
        return LlmResponse(response.text())


class SICLlm(SICConnector):
    component_class = LlmComponent


def main():
    SICComponentManager([LlmComponent])


if __name__ == "__main__":
    main()
