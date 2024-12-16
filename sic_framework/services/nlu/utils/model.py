"""
intent_slot_classification_model.py

This module defines the `BERTNLUModel`, a BERT-based architecture for Natural Language Understanding (NLU),
designed for dual tasks: intent classification and slot filling.

Features:
1. Leverages a pre-trained BERT intent_slot_classification_model (`bert-base-uncased`) for contextual embeddings.
2. Includes separate classification heads for:
   - Intent classification using the [CLS] token output.
   - Slot filling using the token-level embeddings.

Dependencies:
- `torch.nn`: For defining neural network layers and components.
- `transformers.BertModel`: Pre-trained BERT intent_slot_classification_model from Hugging Face's Transformers library.

Usage:
- Initialize the intent_slot_classification_model with the number of intents and slots specific to your task:
    intent_slot_classification_model = BERTNLUModel(num_intents=10, num_slots=20)
- Call the intent_slot_classification_model's `forward` method with tokenized inputs to get predictions:
    intent_logits, slot_logits = intent_slot_classification_model(input_ids, attention_mask)
"""

import torch.nn as nn
from transformers import BertModel


class BERTNLUModel(nn.Module):
    """
    A BERT-based intent_slot_classification_model for Natural Language Understanding (NLU), supporting intent classification
    and slot filling tasks.

    Architecture:
    - Base Model: Pre-trained `BertModel` (`bert-base-uncased`) for generating contextual embeddings.
    - Intent Classifier: A linear layer on top of the [CLS] token output for intent prediction.
    - Slot Classifier: A linear layer applied to the token-level embeddings for slot tagging.

    Args:
        num_intents (int): The number of unique intents for classification.
        num_slots (int): The number of unique slot labels for tagging.

    Methods:
        forward(input_ids, attention_mask):
            Performs a forward pass through the intent_slot_classification_model to generate intent and slot logits.

            Args:
                input_ids (torch.Tensor): Input token IDs (batch_size x seq_length).
                attention_mask (torch.Tensor): Attention mask (batch_size x seq_length).

            Returns:
                tuple:
                    intent_logits (torch.Tensor): Logits for intent classification (batch_size x num_intents).
                    slot_logits (torch.Tensor): Logits for slot tagging (batch_size x seq_length x num_slots).
    """

    def __init__(self, num_intents, num_slots):
        super(BERTNLUModel, self).__init__()
        self.bert = BertModel.from_pretrained("bert-base-uncased")
        self.intent_classifier = nn.Linear(self.bert.config.hidden_size, num_intents)
        self.slot_classifier = nn.Linear(self.bert.config.hidden_size, num_slots)

    def forward(self, input_ids, attention_mask):
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        sequence_output = outputs.last_hidden_state
        pooled_output = outputs.pooler_output

        intent_logits = self.intent_classifier(pooled_output)
        slot_logits = self.slot_classifier(sequence_output)

        return intent_logits, slot_logits
