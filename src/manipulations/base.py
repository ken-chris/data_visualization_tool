"""
Base class for data manipulation operations.

To add a new manipulation, subclass DataManipulation and override:
  - name: str            — display name
  - description: str     — short description shown in config dialog
  - options: dict        — controls to auto-generate in the panel UI, e.g.:
      {
        'method': {
            'type': 'dropdown',
            'label': 'Method',
            'members': ['Option A', 'Option B'],
            'default': 'Option A',
        },
        'scale': {
            'type': 'spinbox',
            'label': 'Scale',
            'min': 0.0,
            'max': 100.0,
            'step': 1.0,
            'default': 1.0,
        },
        'enabled': {
            'type': 'checkbox',
            'label': 'Enabled',
            'default': True,
        },
      }
  - apply(data, timestamps, channel_idx, region, option_values) -> np.ndarray
      Receives the FULL data array for the channel and full timestamps.
      region is (start_time, end_time). Should only modify the slice in the region.
      Returns the full (modified) data array, same shape as input.

Subclasses are automatically added to `manipulation_registry`.
"""
from __future__ import annotations

from typing import List

import numpy as np

manipulation_registry: List[type] = []


class DataManipulation:
    name: str = "Unnamed"
    description: str = ""
    options: dict = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.name != "Unnamed":
            manipulation_registry.append(cls)

    def apply(
        self,
        data: np.ndarray,
        timestamps: np.ndarray,
        channel_idx: int,
        region: tuple,
        option_values: dict,
    ) -> np.ndarray:
        """
        Apply manipulation in-place over the region and return the full array.
        Subclasses must override this method.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement apply()")
