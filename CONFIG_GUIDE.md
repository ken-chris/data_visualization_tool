# Configuration File Guide

## Overview

Config files let you save and restore:
- Annotation labels and colors
- STFT (spectrogram) parameters
- FFT parameters
- UI preferences

## Usage

| Action | Menu | Shortcut |
|--------|------|----------|
| Load config | File → Load Config… | `Ctrl+Shift+O` |
| Save current config | File → Save Config As… | `Ctrl+Shift+S` |

## Example Config File

```json
{
  "labels": [
    { "name": "Walking", "color": [255, 0, 0] },
    { "name": "Running", "color": [0, 200, 0] },
    { "name": "Standing", "color": [0, 0, 255] }
  ],
  "stft": {
    "window_size": 256,
    "overlap": 0.5,
    "window_type": "hann",
    "use_db": true,
    "db_ref": 1e-10,
    "vmin": -80,
    "vmax": 0
  },
  "fft": {
    "nperseg": 256,
    "window": "hann"
  },
  "ui": {
    "plot_height_min": 200,
    "plot_height_max": 250
  },
  "data": {
    "default_sample_rate": 100
  }
}
```

## Parameter Reference

### `labels`
| Key | Type | Description |
|-----|------|-------------|
| `name` | string | Label display text |
| `color` | `[R, G, B]` | RGB color, values 0–255 |

### `stft`
| Key | Type | Description |
|-----|------|-------------|
| `window_size` | int | FFT window size in samples (minimum 64, no upper limit) |
| `overlap` | float | Window overlap fraction (0.0–0.9) |
| `window_type` | string | `"hann"`, `"hamming"`, `"blackman"`, or `"bartlett"` |
| `use_db` | bool | Convert magnitude to dB scale |
| `db_ref` | float | Reference epsilon for `20·log10(magnitude + db_ref)` |
| `vmin` | float | Lower dB display clip (e.g. `-80`) |
| `vmax` | float | Upper dB display clip (e.g. `0`) |

### `fft`
| Key | Type | Description |
|-----|------|-------------|
| `nperseg` | int | Samples per FFT segment (minimum 64, no upper limit) |
| `window` | string | Window function type (same options as STFT) |

### `ui`
| Key | Type | Description |
|-----|------|-------------|
| `plot_height_min` | int | Minimum plot height in pixels |
| `plot_height_max` | int | Maximum plot height in pixels |

### `data`
| Key | Type | Description |
|-----|------|-------------|
| `default_sample_rate` | float | Fallback sample rate in Hz when not in file |

## Tips

- **Share configs** across a team to standardize annotation settings
- **Per-dataset configs** — keep separate files for different data types or studies
- Config files only update settings that are present; omitted keys keep their current values

