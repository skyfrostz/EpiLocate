"""Shared, deliberately simple training and evaluation for the 2D baseline."""
import json
import os
import random
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import confusion_matrix, roc_auc_score
from torch.utils.data import DataLoader

from src.dataset import RICORDDataset

DEVELOPMENT_NOTICE = "SMOKE / DEVELOPMENT ONLY"


def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def resolve_device(requested="auto"):
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def make_loader(csv_path, config, shuffle, batch_size=None):
    dataset = RICORDDataset(csv_path, config)
    generator = torch.Generator().manual_seed(int(config["seed"]))
    return DataLoader(
        dataset,
        batch_size=batch_size or int(config["training"]["batch_size"]),
        shuffle=shuffle,
        num_workers=int(config["training"].get("num_workers", 0)),
        pin_memory=torch.cuda.is_available(),
        generator=generator,
    )


def classification_metrics(labels, probabilities):
    labels = np.asarray(labels, dtype=np.int64)
    probabilities = np.asarray(probabilities, dtype=np.float64)
    if labels.ndim != 1 or probabilities.shape != (len(labels), 2):
        raise ValueError("Invalid labels/probability shape")
    if set(np.unique(labels)) != {0, 1}:
        raise ValueError("Both labels must be present for evaluation")
    if not np.isfinite(probabilities).all():
        raise ValueError("Non-finite prediction probability")
    predictions = probabilities.argmax(axis=1)
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    return {
        "accuracy": float((predictions == labels).mean()),
        "roc_auc": float(roc_auc_score(labels, probabilities[:, 1])),
        "sensitivity": float(tp / (tp + fn)),
        "specificity": float(tn / (tn + fp)),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "sample_count": int(len(labels)),
    }


def train_one_epoch(model, loader, criterion, optimizer, device):
    model.train()
    total_loss = 0.0
    seen = 0
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad(set_to_none=True)
        logits = model(images)
        if not torch.isfinite(logits).all():
            raise FloatingPointError("Non-finite training logits")
        loss = criterion(logits, labels)
        if not torch.isfinite(loss):
            raise FloatingPointError("Non-finite training loss")
        loss.backward()
        optimizer.step()
        total_loss += float(loss.detach().cpu()) * len(labels)
        seen += len(labels)
    value = total_loss / seen
    if not np.isfinite(value):
        raise FloatingPointError("Non-finite epoch training loss")
    return value


@torch.no_grad()
def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    labels_all, probabilities_all = [], []
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        logits = model(images)
        if not torch.isfinite(logits).all():
            raise FloatingPointError("Non-finite evaluation logits")
        loss = criterion(logits, labels)
        probabilities = torch.softmax(logits, dim=1)
        if not torch.isfinite(loss) or not torch.isfinite(probabilities).all():
            raise FloatingPointError("Non-finite evaluation loss/probability")
        total_loss += float(loss.cpu()) * len(labels)
        labels_all.extend(labels.cpu().numpy().tolist())
        probabilities_all.append(probabilities.cpu().numpy())
    probabilities = np.concatenate(probabilities_all)
    metrics = classification_metrics(labels_all, probabilities)
    metrics["loss"] = float(total_loss / len(labels_all))
    return metrics, np.asarray(labels_all), probabilities


def slice_predictions(dataset, labels, probabilities):
    if len(dataset.frame) != len(labels):
        raise ValueError("Prediction count does not match dataset")
    columns = ["patient_id", "study_uid", "series_uid", "image_path"]
    result = dataset.frame[columns].copy()
    result["true_label"] = labels.astype(int)
    result["prob_negative"] = probabilities[:, 0]
    result["prob_positive"] = probabilities[:, 1]
    result["pred_label"] = probabilities.argmax(axis=1)
    result["development_notice"] = DEVELOPMENT_NOTICE
    return result


def patient_predictions(slice_frame):
    records = []
    for patient_id, group in slice_frame.groupby("patient_id", sort=True):
        if group.true_label.nunique() != 1:
            raise ValueError(f"Patient label conflict in predictions: {patient_id}")
        negative = float(group.prob_negative.mean())
        positive = float(group.prob_positive.mean())
        records.append({
            "patient_id": patient_id,
            "study_uid": "|".join(sorted(group.study_uid.unique())),
            "series_uid": "|".join(sorted(group.series_uid.unique())),
            "slice_count": int(len(group)),
            "true_label": int(group.true_label.iloc[0]),
            "prob_negative": negative,
            "prob_positive": positive,
            "pred_label": int(positive >= negative),
            "development_notice": DEVELOPMENT_NOTICE,
        })
    return pd.DataFrame(records)


def save_checkpoint(path, model, optimizer, epoch, val_loss, config):
    torch.save({
        "notice": DEVELOPMENT_NOTICE,
        "epoch": int(epoch),
        "val_loss": float(val_loss),
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "config": config,
    }, path)


def load_model_checkpoint(path, model, device):
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    return checkpoint


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")


def runtime_metadata(device):
    return {
        "notice": DEVELOPMENT_NOTICE,
        "device": str(device),
        "torch_version": torch.__version__,
        "pid": os.getpid(),
    }
