# DataVisualizer

A desktop application for loading, visualizing, annotating, and manipulating multi-channel time series and spatial sensor data.

## Features

- 📂 **Multi-dataset management** — load and manage multiple datasets simultaneously
- 📈 **Time Series viewer** — scrollable, multi-channel plots with pan/zoom, per-channel plot boxes, and linked region selection
- 🌈 **Spectrogram (STFT)** — configurable window size, overlap, window type, and dB scale
- 📊 **FFT Analysis** — frequency domain view of a selected region, per-channel
- 🗺️ **Spatial Data (2D)** — scatter plot with X/Y/size/color channel mapping, time-window masking, and axis range sliders
- 🔧 **Manipulations** — pluggable signal processing operations (normalize, Butterworth filter, Chebyshev filter) applied per-channel to a selected region
- 🏷️ **Annotations** — drag-to-create labeled time regions, resize, edit notes, delete; exported to JSON/CSV
- ➕ **Extensible tabs** — add new visualization widgets via the `+` tab
- 💾 **Session save/load** and annotation export

## Installation

### Prerequisites
- Python 3.10+
- pip

### Setup

```bash
# Clone or download the repository, then:
pip install -r requirements.txt
python src/main.py
```

On Windows you can also double-click **`run.bat`** which installs dependencies and launches the app.

## Quick Start

1. Launch the app — it opens on the **Data Mgmt** tab
2. Click **Load Data** to open a file (CSV, `.npy`, `.h5`)
3. Switch to **Time Series**, **Spectrogram**, or **FFT** tabs to explore the data
4. Use the **`+` tab** to add a **Spatial Data (2D)** widget
5. Configure manipulations via **Edit → Manage Manipulations**

## Data Formats

### CSV
```
timestamp,channel1,channel2,channel3
0.0,0.5,0.3,0.1
0.001,0.6,0.4,0.2
```
Non-numeric (string) columns are loaded as string data objects and are available for use in the Spatial tab's datetime configuration, but are not plotted numerically.

### NumPy (`.npy`)
- 2D array: shape `(n_samples, n_channels+1)` — first column is timestamps

### HDF5 (`.h5`)
- Dataset `data`: 2D array `(n_samples, n_channels+1)`
- Optional attribute: `sample_rate`

## UI Layout

```
┌─────────────────┬────────────────────────────────────────────┐
│  Left Sidebar   │  Tab Area                                  │
│  (context-aware)│  [Time Series] [Spectrogram] [FFT]         │
│                 │  [Data Mgmt]  [Spatial 2D…] [+]            │
│  • Annotation   │                                            │
│    Labels       │  Content depends on active tab             │
│  • Manipulations│                                            │
│  • STFT Params  │                                            │
│  • FFT Params   │                                            │
└─────────────────┴────────────────────────────────────────────┘
```

The left sidebar changes with the active tab:
| Tab | Left Sidebar |
|-----|-------------|
| Time Series | Annotation Labels + Manipulations |
| Spectrogram | STFT Parameters & dB Scale |
| FFT | FFT Parameters |
| Data Mgmt | *(empty)* |
| Spatial 2D | Manipulations |

Sidebar sections are **collapsible**. Both the sidebar and the data box list scroll when content overflows.

## Tabs

### Data Mgmt
- Load data files; each loaded file becomes a named dataset
- View and rename channels; toggle channels for FFT/STFT display
- Duplicate or delete datasets and channels

### Time Series
- One scrollable **Plot Box** per dataset; each box can hold multiple channel traces
- Configure traces via the ⚙ button on each box (add/remove channels, set color/opacity)
- Drag the shaded **region selector** to define a time window for FFT analysis and manipulations
- All plot boxes share synchronized x-axis pan/zoom

### Spectrogram
- STFT heatmap per active channel; adjust parameters in the left sidebar and click **Apply**

### FFT
- Frequency-domain plot of the currently selected region, per active channel

### Spatial Data (2D)
Added via the `+` tab. Configure in **⚙ Settings**:
- **X / Y channels**: axes data
- **Size channel** (optional): point size mapped to 4–24 px
- **Color channel** (optional): viridis colormap (256-level palette for performance)
- **Time file** (optional): external timestamp file with full datetime parsing support (split columns, custom separators)
- **Max displayed rows**: random subsample for performance (default 10,000)

Controls:
- **Time window slider**: scrub through time; set window size and click **Apply**
- **X/Y range sliders**: zoom the plot axes
- **Manipulations** panel in the left sidebar

## Manipulations

Manipulations modify channel data in-place. See [MANIPULATIONS.md](MANIPULATIONS.md) for full documentation.

Built-in manipulations:
- **Normalize** — z-score or min-max normalization
- **Butterworth Filter** — lowpass/highpass/bandpass/bandstop IIR filter
- **Chernav Filter** — Chebyshev Type I filter

Enable/disable manipulations via **Edit → Manage Manipulations**.

On the **Time Series** tab manipulations apply to the **selected region**. On **Spatial** tabs they apply to the **full dataset**.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+O` | Open data file |
| `Ctrl+S` | Save session |
| `Ctrl+E` | Export annotations |
| `Ctrl+Shift+O` | Load config |
| `Ctrl+Shift+S` | Save config |
| `Ctrl+Q` | Quit |

## Performance Notes

- Time series uses `setClipToView(True)` and `setDownsampling(auto=True, method='peak')` — only pixels in view are processed, and point count scales with pixel width automatically
- Spatial color mapping uses a 256-entry pre-built brush palette (viridis) — only 256 `QBrush` objects exist regardless of point count
- Use **Max displayed rows** in Spatial settings to cap render cost on large datasets

## Building a Standalone Executable

```bash
pyinstaller --onefile --windowed --name DataVisualizer src/main.py
```

## License

MIT License

