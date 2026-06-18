# Manipulations

Manipulations are pluggable signal processing operations that modify channel data in-place. They are applied from the **Manipulations** panel in the left sidebar.

## Enabling Manipulations

Go to **Edit → Manage Manipulations** to enable or disable individual manipulations. The state is saved to `manipulation_config.json`.

## Where Manipulations Apply

| Tab | Region |
|-----|--------|
| Time Series | Selected region only (drag the blue region selector first) |
| Spatial 2D | Full dataset |

## Built-in Manipulations

### Normalize (`normalize.py`)

Normalizes channel data within the active region.

| Option | Type | Values | Description |
|--------|------|--------|-------------|
| Method | Dropdown | `Standard Score`, `Min/Max` | Normalization method |

- **Standard Score** (z-score): `(x - mean) / std` — centers at 0, unit variance
- **Min/Max**: `(x - min) / (max - min)` — scales to [0, 1]

---

### Butterworth Filter (`butter_filter.py`)

Applies a zero-phase Butterworth IIR filter (`scipy.signal.butter` + `filtfilt`).

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Method | Dropdown | `Lowpass` | `Lowpass`, `Highpass`, `Bandpass`, `Bandstop` |
| Cutoff Frequency | float | `0.5` | Cutoff in Hz |
| Filter Order | int | `4` | Higher order = sharper rolloff |
| Sample Rate | int | `125` | Sample rate of the data in Hz |

The cutoff is normalized internally as `cutoff / (0.5 * sample_rate)`.

---

### Chernav Filter (`Cher_filter.py`)

Applies a zero-phase Chebyshev Type I filter (`scipy.signal.cheby1` + `filtfilt`). Equiripple in the passband, sharper rolloff than Butterworth at the same order.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| Method | Dropdown | `Lowpass` | `Lowpass`, `Highpass`, `Bandpass`, `Bandstop` |
| Cutoff Frequency | float | `0.5` | Cutoff in Hz |
| Filter Order | int | `4` | Higher order = sharper rolloff |
| Sample Rate | int | `125` | Sample rate of the data in Hz |

---

## Adding a New Manipulation

1. Create a new file in `src/manipulations/`, e.g. `my_manipulation.py`
2. Subclass `DataManipulation` and set `name`, `description`, and `options`
3. Implement `apply()`
4. Import the class in `src/manipulations/__init__.py`

### Minimal example

```python
# src/manipulations/my_manipulation.py
from __future__ import annotations
import numpy as np
from src.manipulations.base import DataManipulation


class MyManipulation(DataManipulation):
    name = "My Manipulation"
    description = "Short description shown in the config dialog."
    options = {
        "scale": {
            "type": "spinbox",
            "label": "Scale factor",
            "min": 0.0,
            "max": 1000.0,
            "step": 0.1,
            "default": 1.0,
        }
    }

    def apply(self, data, timestamps, channel_idx, region, option_values):
        result = data.copy()
        start, end = region
        mask = (timestamps >= start) & (timestamps <= end)
        scale = option_values.get("scale", 1.0)
        result[mask] = result[mask] * scale
        return result
```

Then in `src/manipulations/__init__.py`:
```python
from src.manipulations.my_manipulation import MyManipulation
```

The manipulation will automatically appear in **Edit → Manage Manipulations** and in the sidebar panel.

### `options` field reference

Each key in `options` becomes a labeled control row in the panel UI.

| `type` | Widget | Extra keys |
|--------|--------|------------|
| `"dropdown"` | QComboBox | `members: list[str]`, `default: str` |
| `"spinbox"` | QDoubleSpinBox | `min`, `max`, `step`, `default` (all float) |
| `"checkbox"` | QCheckBox | `default: bool` |
| `"float"` | QLineEdit | `default`, `placeholder` |
| `"int"` | QLineEdit | `default`, `placeholder` |
| `"text"` | QLineEdit | `default`, `placeholder` |

### `apply()` contract

```python
def apply(
    self,
    data: np.ndarray,       # full 1-D array for the channel (n_samples,)
    timestamps: np.ndarray, # full timestamp array (n_samples,)
    channel_idx: int,       # index of the channel being modified
    region: tuple,          # (start_time, end_time) in same units as timestamps
    option_values: dict,    # values from the UI controls
) -> np.ndarray:            # full array, same shape as input
```

- Receive the **full** channel array; modify only the slice indicated by `region`
- Return the full array (same shape as input)
- Raise exceptions freely — errors are caught and shown in a dialog
