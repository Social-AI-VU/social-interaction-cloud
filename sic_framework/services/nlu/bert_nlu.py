import random
import time

import numpy as np
import torch

from sic_framework import SICComponentManager
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.message_python2 import SICConfMessage, SICMessage, SICRequest
from sic_framework.core.utils import is_sic_instance
from sic_framework.services.nlu.utils.dataset import (
    fit_encoders,
    intent_label_encoder,
    slot_label_encoder,
)
from sic_framework.services.nlu.utils.evaluation import predict
from sic_framework.services.nlu.utils.model import BERTNLUModel


class InferenceRequest(SICRequest):
    def __init__(self, inference_text):
        """
        The output text of the ASR component which we want to run inference on.
        """
        super().__init__()
        self.inference_text = inference_text


class InferenceResult(SICMessage):
    def __init__(self, intent, slots, inference_time):
        """
        The NLU inference result.
        """
        self.intent = intent
        self.slots = slots
        self.inference_time = inference_time


class NLUConf(SICConfMessage):
    def __init__(
        self,
        ontology_path: str,
        model_path: str,
        max_length: int = 16,
    ):
        """
        Configuration for the NLU component.
        :param ontology_path        Path to the ontology file.
        :param model_path           Path to the trained model.
        :param max_length           Maximum token length for inputs.
        """
        SICConfMessage.__init__(self)

        self.ontology_path = ontology_path
        self.max_length = max_length
        self.model_path = model_path


class NLUComponent(SICComponent):
    """
    This component listens to InferenceRequest messages, which are the output of any ASR component, such as Dialogflow or Whisper.
    It then runs inference on the text and returns an InferenceResult containing the intent, slots, and inference time

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nlu_is_init = False
        self.init_nlu()

    def init_nlu(self):
        SEED = 42
        random.seed(SEED)
        np.random.seed(SEED)
        torch.manual_seed(SEED)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(SEED)

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        ontology_path = self.params.ontology_path
        fit_encoders(ontology_path)
        self.num_intents = len(intent_label_encoder.classes_)
        self.num_slots = len(slot_label_encoder.classes_)

    def on_request(self, request):
        if not self.nlu_is_init:
            self.init_nlu()

        if is_sic_instance(request, InferenceRequest):
            reply = self.run_inference(request)
            return reply
        raise NotImplementedError("Unknown request type {}".format(type(request)))

    @staticmethod
    def get_conf():
        return NLUConf()

    @staticmethod
    def get_inputs():
        return [InferenceRequest]

    @staticmethod
    def get_output():
        return InferenceResult

    def run_inference(self, request):
        self.logger.info(f"Running inference on example text: {request.inference_text}")
        model = BERTNLUModel(num_intents=self.num_intents, num_slots=self.num_slots).to(
            self.device
        )
        model.load_state_dict(torch.load(self.params.model_path, weights_only=True))

        start_time = time.time()
        intent, slots = predict(
            model,
            request.inference_text,
            max_length=self.params.max_length,
            device=self.device,
        )
        inference_time = time.time() - start_time
        # self.logger.info(f"Inference result: {intent}, {slots}, {inference_time}")
        return InferenceResult(intent, slots, inference_time)


class NLU(SICConnector):
    component_class = NLUComponent


def main():
    SICComponentManager([NLUComponent])


if __name__ == "__main__":
    main()
