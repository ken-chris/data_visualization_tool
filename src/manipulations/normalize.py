"""Normalize manipulation: applies z-score or min-max normalization to a region."""
from __future__ import annotations

import numpy as np

from src.manipulations.base import DataManipulation


class NormalizeManipulation(DataManipulation):
    name = "Normalize"
    description = "Normalize channel data in the selected region."
    options = {
        "method": {
            "type": "dropdown",
            "label": "Method",
            "members": ["Standard Score", "Min/Max"],
            "default": "Standard Score",
        }
    }

    def apply(self, data, timestamps, channel_idx, region, option_values):
        result = data.copy()
        start, end = region
        mask = (timestamps >= start) & (timestamps <= end)
        segment = result[mask]
        if len(segment) == 0:
            return result

        method = option_values.get("method", "Standard Score")
        if method == "Standard Score":
            mean = np.mean(segment)
            std = np.std(segment)
            if std > 0:
                result[mask] = (segment - mean) / std
        else:
            mn, mx = np.min(segment), np.max(segment)
            rng = mx - mn
            if rng > 0:
                result[mask] = (segment - mn) / rng

        return result
