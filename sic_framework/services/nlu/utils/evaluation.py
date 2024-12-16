"""
evaluation.py

This module provides evaluation and inference functionality for a trained Natural Language Understanding (NLU) intent_slot_classification_model designed for intent classification and slot filling tasks.

### Features:
1. **Model Evaluation**:
   - `evaluate`: Assesses intent_slot_classification_model performance on a test dataset, calculating accuracy and generating classification reports for both intents and slots.

2. **Inference**:
   - `predict`: Performs single-sentence inference, outputting the predicted intent and slots in a BIO (Begin-Inside-Outside) format.

### Dependencies:
- `tokenizer`: BERT tokenizer for processing input text.
- `intent_label_encoder`: Encoder to map intent predictions to human-readable labels.
- `slot_label_encoder`: Encoder to map slot predictions to human-readable BIO tags.

### Usage:
- Use `evaluate()` to assess intent_slot_classification_model performance on test run_data, including intent accuracy and detailed classification reports.
- Use `predict()` to infer the intent and slot tags for new user inputs.

### Note:
Ensure the intent_slot_classification_model and label encoders are properly trained and loaded before using these functions.
"""

import torch
from sklearn.metrics import accuracy_score, classification_report

from sic_framework.services.nlu.utils.dataset import (
    intent_label_encoder,
    slot_label_encoder,
    tokenizer,
)


def evaluate(model, test_data, device="cpu"):
    """
    Evaluates the performance of the intent_slot_classification_model on a test dataset, providing accuracy and classification reports for intent classification and slot filling.

    Args:
        model (nn.Module): Trained NLU intent_slot_classification_model.
        test_data (list): List of preprocessed test examples, each containing input IDs, attention masks, intent labels, and slot labels.
        device (str or torch.device): Device to perform evaluation on ("cpu" or "cuda").

    Outputs:
        Prints:
        - Intent accuracy.
        - Classification report for intents.
        - Classification report for slots in BIO format.
    """
    model.to(device)
    model.eval()

    all_intent_preds, all_intent_labels = [], []
    all_slot_preds, all_slot_labels = [], []

    for example in test_data:
        with torch.no_grad():
            # Prepare input run_data and move to the specified device
            input_ids = example["input_ids"].unsqueeze(0).to(device)
            attention_mask = example["attention_mask"].unsqueeze(0).to(device)

            # Get intent_slot_classification_model predictions
            intent_logits, slot_logits = model(input_ids, attention_mask)

            # Intent predictions
            intent_pred = torch.argmax(intent_logits, dim=1).item()
            intent_label = example["intent_label"].item()
            all_intent_preds.append(intent_pred)
            all_intent_labels.append(intent_label)

            # Slot predictions
            slot_preds = torch.argmax(slot_logits, dim=2).squeeze().tolist()
            slot_labels = example["slot_labels"].tolist()
            valid_slot_labels = slot_labels[: len(slot_preds)]  # Match valid lengths
            all_slot_preds.extend(slot_preds)
            all_slot_labels.extend(valid_slot_labels)

    # Compute and display intent accuracy
    intent_accuracy = accuracy_score(all_intent_labels, all_intent_preds)
    intent_class_report = classification_report(
        all_intent_labels, all_intent_preds, target_names=intent_label_encoder.classes_
    )

    # Compute and display slot classification report
    unique_slot_labels = sorted(set(all_slot_labels + all_slot_preds))
    slot_class_report = classification_report(
        all_slot_labels,
        all_slot_preds,
        target_names=[
            slot_label_encoder.inverse_transform([i])[0] for i in unique_slot_labels
        ],
        labels=unique_slot_labels,
    )

    print(f"Intent Accuracy: {intent_accuracy:.4f}")
    print(f"Intent Classification Report:\n{intent_class_report}")
    print(f"Slot Classification Report:\n{slot_class_report}")


def predict(model, text, max_length=16, device="cpu"):
    """
    Performs inference on a single input text, predicting the intent and slot tags in BIO format.

    Args:
        model (nn.Module): Trained NLU intent_slot_classification_model.
        text (str): Input sentence for prediction.
        max_length (int): Maximum token length for padding/truncation.
        device (str or torch.device): Device to perform inference on ("cpu" or "cuda").

    Returns:
        tuple:
        - intent (str): Predicted intent label.
        - slots (list): List of predicted slot tags in BIO format.
    """
    model.to(device)
    model.eval()

    with torch.no_grad():
        # Tokenize and encode the input text
        encoding = tokenizer(
            text,
            return_tensors="pt",
            padding="max_length",
            truncation=True,
            max_length=max_length,
        )

        # Prepare input run_data and move to the specified device
        input_ids = encoding["input_ids"].squeeze().to(device)
        attention_mask = encoding["attention_mask"].squeeze().to(device)

        # Get intent_slot_classification_model predictions
        intent_logits, slot_logits = model(
            input_ids.unsqueeze(0), attention_mask.unsqueeze(0)
        )

        # Decode intent
        intent_pred = torch.argmax(intent_logits, dim=1).item()
        intent = intent_label_encoder.inverse_transform([intent_pred])[0]

        # Decode slots
        slot_preds = torch.argmax(slot_logits, dim=2).squeeze().tolist()
        slots = slot_label_encoder.inverse_transform(slot_preds)

        return intent, slots
