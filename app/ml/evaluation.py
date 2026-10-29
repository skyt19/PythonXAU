"""Model evaluation metrics"""
import logging
from typing import Dict

import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    confusion_matrix,
    classification_report,
)

logger = logging.getLogger(__name__)


def evaluate_model(model, dataloader, device='cpu') -> Dict:
    """Evaluate model on dataset."""
    model.eval()
    all_preds = []
    all_labels = []

    with torch.no_grad():
        for X_batch, y_batch in dataloader:
            X_batch = X_batch.to(device)
            outputs = model(X_batch)
            _, predicted = torch.max(outputs, 1)
            all_preds.extend(predicted.cpu().numpy())
            all_labels.extend(y_batch.numpy())

    y_true = np.array(all_labels)
    y_pred = np.array(all_preds)

    accuracy = accuracy_score(y_true, y_pred)
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, average='macro', zero_division=0
    )

    cm = confusion_matrix(y_true, y_pred)

    class_names = ['TREND', 'RANGE', 'HIGH_VOLATILITY']
    report = classification_report(y_true, y_pred, target_names=class_names)

    logger.info(f"\nAccuracy: {accuracy:.4f}")
    logger.info(f"Macro Precision: {precision:.4f}")
    logger.info(f"Macro Recall: {recall:.4f}")
    logger.info(f"Macro F1: {f1:.4f}")
    logger.info(f"\n{report}")
    logger.info(f"\nConfusion Matrix:\n{cm}")

    return {
        'accuracy': float(accuracy),
        'precision': float(precision),
        'recall': float(recall),
        'f1': float(f1),
        'confusion_matrix': cm.tolist(),
        'predictions': y_pred.tolist(),
        'labels': y_true.tolist(),
    }
