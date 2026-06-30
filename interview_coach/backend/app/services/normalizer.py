"""Landmark normalization utilities."""

import numpy as np

from app.utils.constants import DYNAMIC_FEATURE_DIM, STATIC_FEATURE_DIM


def normalize_sequence(sequence: np.ndarray) -> np.ndarray:
    seq = sequence.copy().reshape(-1, 75, 3)
    left_shoulder = seq[:, 11, :]
    right_shoulder = seq[:, 12, :]
    center = (left_shoulder + right_shoulder) / 2.0
    shoulder_width = np.linalg.norm(left_shoulder - right_shoulder, axis=1, keepdims=True)
    shoulder_width = np.maximum(shoulder_width, 1e-4)
    seq = (seq - center[:, None, :]) / shoulder_width[:, None, :]
    return seq.reshape(-1, DYNAMIC_FEATURE_DIM)


def resample_sequence(sequence: np.ndarray, target_len: int) -> np.ndarray:
    t, dim = sequence.shape
    if t == target_len:
        return sequence
    if t < 2:
        return np.zeros((target_len, dim), dtype=np.float32)
    x_old = np.linspace(0, 1, t)
    x_new = np.linspace(0, 1, target_len)
    out = np.zeros((target_len, dim), dtype=np.float32)
    for j in range(dim):
        out[:, j] = np.interp(x_new, x_old, sequence[:, j])
    return out


def normalize_static(frame_vec: np.ndarray) -> np.ndarray:
    pts = frame_vec.reshape(21, 3).copy()
    wrist = pts[0]
    ref = pts[5]
    pts -= wrist
    scale = np.linalg.norm(ref - wrist)
    if scale < 1e-4:
        scale = 1.0
    pts /= scale
    return pts.reshape(STATIC_FEATURE_DIM)