#!/usr/bin/env python3
"""Step 9/10 training entry point for smoke and baseline experiments."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import torch
from torch import nn

from src.data_checks import PROJECT_ROOT, load_config
from src.model import build_model
from src.training import (DEVELOPMENT_NOTICE, classification_metrics, evaluate,
                          load_model_checkpoint, make_loader, patient_predictions,
                          resolve_device, runtime_metadata, save_checkpoint,
                          seed_everything, slice_predictions, train_one_epoch, write_json)


def require_completed_gates(experiment):
    eligibility_path = PROJECT_ROOT / "outputs/data/baseline_eligibility.summary.json"
    if not eligibility_path.is_file():
        raise RuntimeError("Run Step 7.5 baseline eligibility before training")
    eligibility = json.loads(eligibility_path.read_text(encoding="utf-8"))
    if eligibility.get("patient_leakage") != 0 or eligibility.get("split_assignment_changed") is not False:
        raise RuntimeError("Eligibility/split safety gate did not pass")
    tiny_path = PROJECT_ROOT / "outputs/experiments/EXP000_tiny_overfit/metrics.json"
    if not tiny_path.is_file() or not json.loads(tiny_path.read_text(encoding="utf-8")).get("passed"):
        raise RuntimeError("Run and pass Step 8 tiny overfit before training")
    if experiment == "baseline":
        smoke_path = PROJECT_ROOT / "outputs/experiments/EXP001_smoke/metrics.json"
        if not smoke_path.is_file():
            raise RuntimeError("Run Step 9 smoke training before the baseline")
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        required = ("checkpoint_reload_inference_verified", "finite_loss_logits_probabilities",
                    "both_labels_verified")
        if not all(smoke.get(key) is True for key in required):
            raise RuntimeError("Step 9 smoke safety gate did not pass")


def save_predictions(out, name, loader, labels, probabilities):
    slices = slice_predictions(loader.dataset, labels, probabilities)
    patients = patient_predictions(slices)
    slices.to_csv(out / f"{name}_predictions.csv", index=False)
    patients.to_csv(out / f"{name}_patient_predictions.csv", index=False)
    patient_metrics = classification_metrics(
        patients.true_label.to_numpy(), patients[["prob_negative", "prob_positive"]].to_numpy()
    )
    return slices, patients, patient_metrics


def run(config, experiment):
    require_completed_gates(experiment)
    smoke = experiment == "smoke"
    name = "EXP001_smoke" if smoke else "EXP002_resnet18_baseline"
    epochs = 1 if smoke else int(config["training"]["epochs"])
    out = PROJECT_ROOT / "outputs/experiments" / name
    out.mkdir(parents=True, exist_ok=True)
    seed_everything(int(config["seed"]))
    device = resolve_device(config["training"].get("device", "auto"))
    train_loader = make_loader(config["data"]["train_csv"], config, shuffle=True)
    val_loader = make_loader(config["data"]["val_csv"], config, shuffle=False)
    if set(train_loader.dataset.frame.label) != {"0", "1"} or set(val_loader.dataset.frame.label) != {"0", "1"}:
        raise ValueError("Both labels must be present in train and validation")

    model = build_model(config).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=float(config["training"]["learning_rate"]),
        weight_decay=float(config["training"]["weight_decay"])
    )
    run_config = {
        **runtime_metadata(device),
        "experiment": name,
        "seed": int(config["seed"]),
        "model": "ResNet18",
        "weights": "ImageNet pretrained",
        "input": [3, int(config["preprocessing"]["image_size"]), int(config["preprocessing"]["image_size"])],
        "num_classes": 2,
        "loss": "CrossEntropyLoss",
        "optimizer": "AdamW",
        "learning_rate": float(config["training"]["learning_rate"]),
        "weight_decay": float(config["training"]["weight_decay"]),
        "batch_size": int(config["training"]["batch_size"]),
        "epochs": epochs,
        "checkpoint_selection": "minimum validation loss; test set is not used",
        "train_csv": config["data"]["train_csv"],
        "val_csv": config["data"]["val_csv"],
    }
    write_json(out / "config.json", run_config)
    log_rows, best_loss, best_epoch = [], float("inf"), None
    checkpoint_path = out / "best_model.pth"
    for epoch in range(1, epochs + 1):
        train_loss = train_one_epoch(model, train_loader, criterion, optimizer, device)
        val_metrics, _, _ = evaluate(model, val_loader, criterion, device)
        row = {
            "notice": DEVELOPMENT_NOTICE,
            "epoch": epoch,
            "train_loss": train_loss,
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
            "val_roc_auc": val_metrics["roc_auc"],
            "val_sensitivity": val_metrics["sensitivity"],
            "val_specificity": val_metrics["specificity"],
            "val_tn": val_metrics["confusion_matrix"][0][0],
            "val_fp": val_metrics["confusion_matrix"][0][1],
            "val_fn": val_metrics["confusion_matrix"][1][0],
            "val_tp": val_metrics["confusion_matrix"][1][1],
            "learning_rate": optimizer.param_groups[0]["lr"],
        }
        log_rows.append(row)
        pd.DataFrame(log_rows).to_csv(out / "train_log.csv", index=False)
        if val_metrics["loss"] < best_loss:
            best_loss, best_epoch = val_metrics["loss"], epoch
            save_checkpoint(checkpoint_path, model, optimizer, epoch, best_loss, run_config)
        print(f"{name} epoch {epoch:02d}/{epochs}: train_loss={train_loss:.6f} "
              f"val_loss={val_metrics['loss']:.6f} val_auc={val_metrics['roc_auc']:.4f}", flush=True)

    reloaded_config = {**config, "model": {**config["model"], "pretrained": False}}
    reloaded = build_model(reloaded_config).to(device)
    checkpoint = load_model_checkpoint(checkpoint_path, reloaded, device)
    val_metrics, val_labels, val_probabilities = evaluate(reloaded, val_loader, criterion, device)
    _, _, val_patient_metrics = save_predictions(
        out, "val", val_loader, val_labels, val_probabilities
    )
    metrics = {
        **runtime_metadata(device),
        "experiment": name,
        "best_epoch": int(best_epoch),
        "checkpoint_metric": "val_loss",
        "best_validation_loss": float(best_loss),
        "checkpoint_reload_epoch": int(checkpoint["epoch"]),
        "checkpoint_reload_inference_verified": True,
        "finite_loss_logits_probabilities": True,
        "both_labels_verified": True,
        "validation_slice_level": val_metrics,
        "validation_patient_level": val_patient_metrics,
    }
    if not smoke:
        test_loader = make_loader(config["data"]["test_csv"], config, shuffle=False)
        test_metrics, test_labels, test_probabilities = evaluate(reloaded, test_loader, criterion, device)
        _, _, test_patient_metrics = save_predictions(
            out, "test", test_loader, test_labels, test_probabilities
        )
        metrics["test_slice_level"] = test_metrics
        metrics["test_patient_level"] = test_patient_metrics
        metrics["test_role"] = "final evaluation only; not used for checkpoint selection"
    write_json(out / "metrics.json", metrics)
    print(f"Completed {name}; best epoch={best_epoch}, checkpoint reload/inference=PASS", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/baseline.yaml")
    parser.add_argument("--experiment", choices=["smoke", "baseline"], required=True)
    args = parser.parse_args()
    try:
        run(load_config(args.config), args.experiment)
    except Exception as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        raise
