"""Normalize manipulation: applies z-score or min-max normalization to a region."""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt

from src.manipulations.base import DataManipulation


class ButterFilterManipulation(DataManipulation):
    name = "Butterworth Filter"
    description = "Apply a Butterworth filter to the selected region."
    options = {
        "method": {
            "type": "dropdown",
            "label": "Method",
            "members": ["Lowpass", "Highpass", "Bandpass", "Bandstop"],
            "default": "Lowpass",
        },
        "cutoff": {
            "type": "float",
            "label": "Cutoff Frequency",
            "default": 0.5,
            "placeholder": 0.5,
        },
        "order": {
            "type": "int",
            "label": "Filter Order",
            "default": 4,
            "placeholder": 4,

        },
        "sample_rate": {
            "type": "int",
            "label": "Sample Rate",
            "default": 125,
            "placeholder": 125,
        }        
    }

    def apply(self, data, timestamps, channel_idx, region, option_values):
        result = data.copy()
        start, end = region
        mask = (timestamps >= start) & (timestamps <= end)
        segment = result[mask]
        if len(segment) == 0:
            return result

        method = option_values.get("method", "Lowpass")
        cutoff = option_values.get("cutoff", 0.5)
        order = option_values.get("order", 4)
        sample_rate = option_values.get("sample_rate", 125)
        nyquist = 0.5 * sample_rate
        normalized_cutoff = cutoff / nyquist
        b, a = butter(order, normalized_cutoff, btype=method.lower())
        filtered_segment = filtfilt(b, a, segment)
        result[mask] = filtered_segment

        return result
