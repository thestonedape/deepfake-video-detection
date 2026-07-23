from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn
from torchvision import models


IMAGE_SIZE = 224
FRAMES_PER_VIDEO = 10
MEAN = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).view(3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).view(3, 1, 1)
LABELS = {0: "fake", 1: "real"}


def build_backbone(name: str, use_pretrained: bool):
    if name == "resnet18":
        builder = models.resnet18
        weights_enum = getattr(models, "ResNet18_Weights", None)
        backbone_type = "resnet"
    elif name == "resnet50":
        builder = models.resnet50
        weights_enum = getattr(models, "ResNet50_Weights", None)
        backbone_type = "resnet"
    elif name == "efficientnet_b4":
        builder = models.efficientnet_b4
        weights_enum = getattr(models, "EfficientNet_B4_Weights", None)
        backbone_type = "efficientnet"
    else:
        raise ValueError(f"Unsupported backbone: {name}")

    model = None
    if use_pretrained and weights_enum is not None:
        try:
            model = builder(weights=weights_enum.DEFAULT)
        except Exception:
            model = None

    if model is None:
        try:
            model = builder(weights=None)
        except TypeError:
            model = builder(pretrained=False)

    if backbone_type == "resnet":
        feature_dim = int(model.fc.in_features)
        encoder = nn.Sequential(*list(model.children())[:-2])
        pool = nn.AdaptiveAvgPool2d(1)
    else:
        feature_dim = int(model.classifier[1].in_features)
        encoder = model.features
        pool = model.avgpool

    return encoder, pool, feature_dim


def extract_frequency_features(images: torch.Tensor, radial_bins: int = 8) -> torch.Tensor:
    gray = images.mean(dim=1)
    height, width = gray.shape[-2:]
    hann_h = torch.hann_window(height, periodic=False, device=images.device)
    hann_w = torch.hann_window(width, periodic=False, device=images.device)
    hann_2d = hann_h[:, None] * hann_w[None, :]
    windowed = gray * hann_2d.unsqueeze(0)

    fft = torch.fft.fft2(windowed)
    fft = torch.fft.fftshift(fft, dim=(-2, -1))
    magnitude = torch.log1p(torch.abs(fft))

    yy, xx = torch.meshgrid(
        torch.arange(height, device=images.device),
        torch.arange(width, device=images.device),
        indexing="ij",
    )
    cy = (height - 1) / 2.0
    cx = (width - 1) / 2.0
    radius = torch.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    max_radius = radius.max().clamp(min=1.0)
    band_edges = torch.linspace(0, max_radius, radial_bins + 1, device=images.device)

    fft_features = []
    for idx in range(radial_bins):
        mask = (radius >= band_edges[idx]) & (radius < band_edges[idx + 1])
        mask = mask.unsqueeze(0)
        masked = magnitude * mask
        denom = mask.sum(dim=(-2, -1)).clamp(min=1)
        fft_features.append(masked.sum(dim=(-2, -1)) / denom)
    fft_features = torch.stack(fft_features, dim=1)

    dct_like = torch.nn.functional.adaptive_avg_pool2d(gray.unsqueeze(1), (4, 4)).flatten(1)
    return torch.cat([fft_features, dct_like], dim=1)


class FrequencyMLP(nn.Module):
    def __init__(self, input_dim: int = 24, hidden_dim: int = 512, output_dim: int = 1024):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, output_dim),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class DeepfakeImageDetector(nn.Module):
    def __init__(self, backbone: str = "efficientnet_b4", use_pretrained: bool = False):
        super().__init__()
        self.encoder, self.pool, spatial_dim = build_backbone(backbone, use_pretrained)
        self.frequency_mlp = FrequencyMLP(input_dim=24, hidden_dim=512, output_dim=1024)
        fused_dim = spatial_dim + 1024
        self.classifier = nn.Sequential(
            nn.Linear(fused_dim, 1024),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(1024, 512),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(512, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(256, 2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        spatial_features = self.encoder(x)
        spatial_features = self.pool(spatial_features).flatten(1)
        frequency_features = self.frequency_mlp(extract_frequency_features(x))
        fused = torch.cat([spatial_features, frequency_features], dim=1)
        return self.classifier(fused)


def sample_frame_indices(frame_count: int, frames_per_video: int) -> np.ndarray:
    if frame_count <= 0:
        return np.zeros(frames_per_video, dtype=int)
    if frame_count >= frames_per_video:
        return np.linspace(0, frame_count - 1, num=frames_per_video, dtype=int)
    padding = np.full(frames_per_video - frame_count, frame_count - 1, dtype=int)
    return np.concatenate([np.arange(frame_count, dtype=int), padding])


def load_sampled_video_frames(
    video_path: Path,
    frames_per_video: int = FRAMES_PER_VIDEO,
) -> tuple[list[np.ndarray], int]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if frame_count <= 0:
        capture.release()
        raise RuntimeError(f"Unable to determine frame count for: {video_path}")

    frame_indices = sample_frame_indices(frame_count, frames_per_video)
    frames_by_index: dict[int, np.ndarray] = {}
    try:
        for frame_index in np.unique(frame_indices):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
            success, frame = capture.read()
            if not success:
                break
            frames_by_index[int(frame_index)] = frame
    finally:
        capture.release()

    required_indices = {int(index) for index in frame_indices}
    if set(frames_by_index) != required_indices:
        # Some codecs do not support random seeking. Decode sequentially while
        # retaining only the requested frames so memory use remains bounded.
        capture = cv2.VideoCapture(str(video_path))
        frames_by_index = {}
        try:
            current_index = 0
            while current_index <= int(frame_indices[-1]):
                success, frame = capture.read()
                if not success:
                    break
                if current_index in required_indices:
                    frames_by_index[current_index] = frame
                current_index += 1
        finally:
            capture.release()

    if not frames_by_index:
        raise RuntimeError(f"Unable to read any frames from: {video_path}")

    last_good_frame = frames_by_index[max(frames_by_index)]
    sampled_frames = [
        frames_by_index.get(int(index), last_good_frame)
        for index in frame_indices
    ]
    return sampled_frames, frame_count


def preprocess_frame(frame: np.ndarray) -> torch.Tensor:
    resized = cv2.resize(frame, (IMAGE_SIZE, IMAGE_SIZE), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(rgb).float().permute(2, 0, 1) / 255.0
    tensor = (tensor - MEAN) / STD
    return tensor


@dataclass
class PredictionResult:
    predicted_label: str
    confidence: float
    probabilities: dict[str, float]
    frame_count: int
    sampled_frames: int


class DeepfakeService:
    def __init__(self, model_path: Path, device: torch.device | None = None):
        self.model_path = model_path
        if not self.model_path.exists():
            raise RuntimeError(f"Model checkpoint not found: {self.model_path}")
        with self.model_path.open("rb") as checkpoint_file:
            checkpoint_header = checkpoint_file.read(100)
        if checkpoint_header.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise RuntimeError(
                "best_model.pt is a Git LFS pointer, not the downloaded checkpoint"
            )
        self.device = device or torch.device("cpu")
        self.batch_size = max(1, int(os.getenv("INFERENCE_BATCH_SIZE", "1")))
        torch.set_num_threads(max(1, int(os.getenv("TORCH_NUM_THREADS", "1"))))
        self.model = DeepfakeImageDetector(backbone="efficientnet_b4", use_pretrained=False).to(self.device)
        state_dict = torch.load(self.model_path, map_location="cpu", weights_only=True)
        self.model.load_state_dict(state_dict)
        self.model.eval()

    def predict_video(self, video_path: Path) -> PredictionResult:
        selected_frames, frame_count = load_sampled_video_frames(video_path)
        probability_sum = torch.zeros(2, dtype=torch.float32)

        with torch.inference_mode():
            for start in range(0, len(selected_frames), self.batch_size):
                frame_batch = selected_frames[start : start + self.batch_size]
                batch = torch.stack(
                    [preprocess_frame(frame) for frame in frame_batch]
                ).to(self.device)
                logits = self.model(batch)
                probability_sum += torch.softmax(logits, dim=1).sum(dim=0).cpu()

        mean_probs = probability_sum / len(selected_frames)

        fake_prob = float(mean_probs[0].item())
        real_prob = float(mean_probs[1].item())
        predicted_index = int(mean_probs.argmax().item())

        return PredictionResult(
            predicted_label=LABELS[predicted_index],
            confidence=float(mean_probs[predicted_index].item()),
            probabilities={"fake": fake_prob, "real": real_prob},
            frame_count=frame_count,
            sampled_frames=len(selected_frames),
        )
