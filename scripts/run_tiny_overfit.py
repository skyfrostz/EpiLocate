#!/usr/bin/env python3
"""Step 8: deterministic 32-slice overfit gate before any full training."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from torch import nn

from src.data_checks import PROJECT_ROOT, load_config, read_manifest
from src.model import build_model
from src.training import (DEVELOPMENT_NOTICE, evaluate, make_loader, resolve_device,
                          runtime_metadata, seed_everything, train_one_epoch, write_json)


def select_fixed_slices(train, count, seed):
    if count % 2:
        raise ValueError("Tiny slice count must be even")
    selected = []
    per_label = count // 2
    for label in ("0", "1"):
        group = train[train.label.eq(label)].copy()
        group["instance_sort"] = pd.to_numeric(group.instance_number, errors="coerce")
        group = group.sort_values(["patient_id", "series_uid", "instance_sort", "image_path"])
        if len(group) < per_label:
            raise ValueError(f"Not enough training slices for label {label}")
        positions = np.linspace(0, len(group) - 1, per_label, dtype=int)
        selected.append(group.iloc[positions].drop(columns="instance_sort"))
    result = pd.concat(selected).sample(frac=1, random_state=seed).reset_index(drop=True)
    expected = {"0": per_label, "1": per_label}
    if len(result) != count or result.label.value_counts().to_dict() != expected:
        raise AssertionError("Tiny selection is not balanced and fixed")
    return result


def main(config):
    settings = config["tiny_overfit"]
    out = PROJECT_ROOT / "outputs/experiments/EXP000_tiny_overfit"
    out.mkdir(parents=True, exist_ok=True)
    train = read_manifest(config["data"]["train_csv"])
    tiny = select_fixed_slices(train, int(settings["slice_count"]), int(config["seed"]))
    tiny["development_notice"] = DEVELOPMENT_NOTICE
    manifest = out / "tiny_manifest.csv"
    tiny.to_csv(manifest, index=False, lineterminator="\n")

    seed_everything(int(config["seed"]))
    device = resolve_device(config["training"].get("device", "auto"))
    loader = make_loader(manifest, config, shuffle=True, batch_size=int(settings["batch_size"]))
    eval_loader = make_loader(manifest, config, shuffle=False, batch_size=int(settings["batch_size"]))
    model = build_model(config).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(settings["learning_rate"]),
                                  weight_decay=float(config["training"]["weight_decay"]))
    rows = []
    for epoch in range(1, int(settings["epochs"]) + 1):
        train_loss = train_one_epoch(model, loader, criterion, optimizer, device)
        metrics, _, _ = evaluate(model, eval_loader, criterion, device)
        rows.append({"notice": DEVELOPMENT_NOTICE, "epoch": epoch, "train_loss": train_loss,
                     "evaluation_loss": metrics["loss"], "training_accuracy": metrics["accuracy"]})
        print(f"Tiny epoch {epoch:02d}: loss={metrics['loss']:.6f} accuracy={metrics['accuracy']:.4f}", flush=True)
        first_loss = rows[0]["evaluation_loss"]
        reduction = 1.0 - metrics["loss"] / first_loss if first_loss else 0.0
        if (metrics["accuracy"] >= float(settings["min_accuracy"])
                and metrics["loss"] <= float(settings["max_final_loss"])
                and reduction >= float(settings["min_loss_reduction_fraction"])):
            break
    log = pd.DataFrame(rows)
    log.to_csv(out / "train_log.csv", index=False)
    reduction = 1.0 - log.evaluation_loss.iloc[-1] / log.evaluation_loss.iloc[0]
    passed = bool(log.training_accuracy.iloc[-1] >= float(settings["min_accuracy"])
                  and log.evaluation_loss.iloc[-1] <= float(settings["max_final_loss"])
                  and reduction >= float(settings["min_loss_reduction_fraction"]))
    result = {
        **runtime_metadata(device),
        "passed": passed,
        "slice_count": len(tiny),
        "positive_slices": int(tiny.label.eq("1").sum()),
        "negative_slices": int(tiny.label.eq("0").sum()),
        "epochs_run": len(log),
        "initial_evaluation_loss": float(log.evaluation_loss.iloc[0]),
        "final_evaluation_loss": float(log.evaluation_loss.iloc[-1]),
        "final_training_accuracy": float(log.training_accuracy.iloc[-1]),
        "loss_reduction_fraction": float(reduction),
        "success_thresholds": {
            "min_accuracy": float(settings["min_accuracy"]),
            "max_final_loss": float(settings["max_final_loss"]),
            "min_loss_reduction_fraction": float(settings["min_loss_reduction_fraction"]),
        },
    }
    write_json(out / "metrics.json", result)
    write_json(out / "config.json", {"notice": DEVELOPMENT_NOTICE, "seed": config["seed"],
                                      "model": config["model"], "tiny_overfit": settings})
    fig, axis = plt.subplots(figsize=(7, 4))
    axis.plot(log.epoch, log.train_loss, marker="o", markersize=3, label="optimization train loss")
    axis.plot(log.epoch, log.evaluation_loss, marker="o", markersize=3,
              linestyle="--", label="train-set loss in eval mode")
    axis.set(xlabel="Epoch", ylabel="Loss", title=f"Tiny overfit loss - {DEVELOPMENT_NOTICE}")
    axis.set_yscale("log")
    axis.grid(alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(out / "loss_curve.png", dpi=160)
    plt.close(fig)
    print(f"Tiny overfit gate: {'PASS' if passed else 'FAIL'}", flush=True)
    if not passed:
        raise RuntimeError("Tiny overfit did not reach its predeclared thresholds; stop before smoke training")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/baseline.yaml")
    args = parser.parse_args()
    try:
        main(load_config(args.config))
    except Exception as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        raise SystemExit(1)
