"""Torchvision ResNet-18 with an ImageNet backbone and a new two-class head."""
from torch import nn
from torchvision.models import ResNet18_Weights, resnet18

from src.data_checks import load_config


def build_model(config=None):
    config = load_config() if config is None else config
    settings = config["model"]
    if settings["name"] != "resnet18" or int(settings["num_classes"]) != 2:
        raise ValueError("This baseline requires resnet18 with two output classes")
    if not isinstance(settings["pretrained"], bool):
        raise ValueError("model.pretrained must be a YAML boolean")
    weights = ResNet18_Weights.DEFAULT if settings["pretrained"] else None
    model = resnet18(weights=weights)
    model.fc = nn.Linear(model.fc.in_features, 2)
    return model
