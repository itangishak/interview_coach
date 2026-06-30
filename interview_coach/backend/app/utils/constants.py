"""Shared constants for demo and production modes."""

DEMO_DYNAMIC_SIGNS = [
    "hello", "thank you", "please", "sorry", "water", "help",
    "yes", "no", "family", "friend", "school", "work",
]

DEMO_STATIC_SIGNS = list("ABCDEFGHIKLMNOPQRSTUVWXY") + [str(i) for i in range(10)]

POSE_LANDMARKS = 33
HAND_LANDMARKS = 21
DYNAMIC_FEATURE_DIM = 225
STATIC_FEATURE_DIM = 63