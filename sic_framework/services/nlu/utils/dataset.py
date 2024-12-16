"""
dataset.py

This module provides core functionality for preparing and managing run_data in a Natural Language Understanding (NLU) pipeline, specifically for intent classification and slot filling tasks. It includes ontology loading, label encoding, tokenization, and dataset preparation for PyTorch-based models.

### Features:
1. **Ontology Loading and Label Encoding**:
   - Loads ontology run_data (intents and slots) from a JSON file.
   - Encodes intents and slot labels into integers using sklearn's LabelEncoder, with support for BIO (Begin-Inside-Outside) tagging.

2. **Data Loading and Preprocessing**:
   - `load_data`: Loads examples from JSON files.
   - `process_example`: Tokenizes text and generates BIO slot labels.
   - `preprocess_data`: Converts raw run_data into a tokenized and padded format suitable for intent_slot_classification_model input.

3. **NLURecipeDataset Class**:
   - PyTorch Dataset class for batching and iterating over preprocessed run_data.
   - Provides tensors for input IDs, attention masks, intent labels, and slot labels.

### Components:
- `tokenizer`: Pre-trained BERT tokenizer for text tokenization.
- `intent_label_encoder`: Encodes intents into integer labels.
- `slot_label_encoder`: Encodes slot labels into BIO-format integers.

### Usage:
- Use `fit_encoders()` to initialize label encoders based on the ontology JSON.
- Use `preprocess_data()` to convert raw run_data into a format ready for training and evaluation.
- Use `NLURecipeDataset` with a PyTorch DataLoader for batching during intent_slot_classification_model training.

### Note:
Requires an `ontology.json` file containing intents and slot types.
"""

import json
import os

import torch
from sklearn.preprocessing import LabelEncoder
from torch.utils.data import Dataset
from transformers import BertTokenizer

# Initialize BERT tokenizer and label encoders
tokenizer = BertTokenizer.from_pretrained("bert-base-uncased")
intent_label_encoder = LabelEncoder()
slot_label_encoder = LabelEncoder()


def load_ontology(ontology_path):
    """
    Loads the ontology from a JSON file, including intents and slots.

    Args:
        ontology_path (str): Path to the ontology JSON file.

    Returns:
        dict: Dictionary containing intents and slot definitions.
    """
    with open(ontology_path, "r") as file:
        ontology = json.load(file)
    return ontology


def fit_encoders(ontology_path):
    """
    Fits intent and slot label encoders using the ontology run_data.

    Args:
        ontology_path (str): Path to the ontology JSON file.
    """
    ontology = load_ontology(ontology_path)
    intents = ontology["intents"]
    slots = ontology["slots"]

    # Fit encoders for intents and BIO-format slots
    intent_label_encoder.fit(intents)
    all_slot_tags = (
        ["O"]
        + [f"B-{slot}" for slot in slots.keys()]
        + [f"I-{slot}" for slot in slots.keys()]
    )
    slot_label_encoder.fit(all_slot_tags)


def process_example(example):
    """
    Tokenizes text and generates BIO-format slot labels.

    Args:
        example (dict): Example containing 'text' and 'slots'.

    Returns:
        tuple:
            - tokens (list): Tokenized text.
            - intent (int): Encoded intent label.
            - slot_labels (list): Encoded BIO-format slot labels.
    """
    tokens = tokenizer.tokenize(example["text"])
    slots = ["O"] * len(tokens)

    # Generate BIO tags for slots
    for slot_type, slot_value in example["slots"].items():
        slot_value_tokens = tokenizer.tokenize(slot_value)
        for i in range(len(tokens) - len(slot_value_tokens) + 1):
            if tokens[i : i + len(slot_value_tokens)] == slot_value_tokens:
                slots[i] = f"B-{slot_type}"
                for j in range(1, len(slot_value_tokens)):
                    slots[i + j] = f"I-{slot_type}"
                break

    intent = intent_label_encoder.transform([example["intent"]])[0]
    slot_labels = slot_label_encoder.transform(slots)

    return tokens, intent, slot_labels


def load_data(file_path):
    """
    Loads dataset examples from a JSON file.

    Args:
        file_path (str): Path to the JSON file.

    Returns:
        list: List of examples, where each example is a dictionary with 'text' and 'slots'.
    """
    with open(file_path, "r") as f:
        data = json.load(f)
    return data


def preprocess_data(data, max_length=16):
    """
    Preprocesses run_data to tokenize text, encode intents and slots, and pad sequences.

    Args:
        data (list): List of examples with 'text' and 'slots'.
        max_length (int): Maximum sequence length for padding.

    Returns:
        list: List of preprocessed examples, each containing:
            - input_ids (torch.Tensor): Tokenized input IDs.
            - attention_mask (torch.Tensor): Attention mask for padding.
            - intent_label (torch.Tensor): Encoded intent label.
            - slot_labels (torch.Tensor): Padded BIO slot labels.
    """
    processed_data = []
    for example in data:
        tokens, intent, slot_labels = process_example(example)
        encoding = tokenizer(
            example["text"],
            return_tensors="pt",
            padding="max_length",
            truncation=True,
            max_length=max_length,
        )
        input_ids = encoding["input_ids"].squeeze()
        attention_mask = encoding["attention_mask"].squeeze()

        # Pad slot labels
        padded_slot_labels = list(slot_labels) + [
            slot_label_encoder.transform(["O"])[0]
        ] * (max_length - len(slot_labels))
        padded_slot_labels = padded_slot_labels[:max_length]

        processed_data.append(
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "intent_label": torch.tensor(intent),
                "slot_labels": torch.tensor(padded_slot_labels),
            }
        )
    return processed_data


class NLURecipeDataset(Dataset):
    """
    PyTorch Dataset for intent classification and slot filling tasks.

    Args:
        data (list): Preprocessed run_data examples.
        ontology (dict): Ontology with intents and slots.
        max_length (int): Maximum sequence length.

    Returns:
        dict: A dictionary containing:
            - input_ids: Tokenized input IDs.
            - attention_mask: Attention mask for padding.
            - intent_label: Encoded intent label.
            - slot_labels: Padded BIO slot labels.
    """

    def __init__(self, data, ontology, max_length=16):
        self.data = data
        self.intent_classes = ontology["intents"]
        self.slot_classes = (
            ["O"]
            + [f"B-{slot}" for slot in ontology["slots"].keys()]
            + [f"I-{slot}" for slot in ontology["slots"].keys()]
        )
        self.max_length = max_length

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        example = self.data[idx]
        return {
            "input_ids": example["input_ids"],
            "attention_mask": example["attention_mask"],
            "intent_label": example["intent_label"],
            "slot_labels": example["slot_labels"],
        }
