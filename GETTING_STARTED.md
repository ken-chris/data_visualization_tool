# Getting Started

## Installation

1. **Install Python 3.10+** — https://www.python.org/ (check "Add Python to PATH")

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   On Windows you can also double-click **`run.bat`** which handles this automatically.

3. **Run the application:**
   ```bash
   python src/main.py
   ```

## First Steps

### Load Data
The app opens on the **Data Mgmt** tab.

1. Click **Load Data** (or **File > Open** / `Ctrl+O`)
2. Select a CSV, NumPy (`.npy`), or HDF5 (`.h5`) file
3. The dataset appears in the Data Mgmt panel with all channels listed
4. Rename channels and toggle them for FFT/Spectrogram use, then click **Apply**

Sample data is available in `sample_data/`. To generate more:
```bash
python generate_sample_data.py
```

### Explore Data

Switch tabs using the tab bar at the top:

- **Time Series** — scrollable multi-channel plots; pan (drag), zoom (scroll wheel)
- **Spectrogram** — STFT heatmap; adjust parameters in the left sidebar and click **Apply STFT Parameters**
- **FFT** — frequency domain of the current region selection

### Select a Region (Time Series)
Drag the blue shaded **region selector** on any plot. All channels stay synchronized.
The selected region is used by:
- FFT analysis (auto-updates as you drag)
- Manipulations (apply to the region only)

### Add Channels to a Plot Box
Each dataset gets a **Plot Box** in the Time Series tab. Click ⚙ on a box to:
- Add or remove channel traces
- Set trace color and opacity

### Annotate
1. Open the **Annotation Labels** collapsible section in the left sidebar (Time Series tab)
2. Add labels and pick colors
3. Select a label, drag a region, click **Create Annotation from Region**
4. Right-click annotations to edit notes or delete
5. Export with **File > Export Annotations** (`Ctrl+E`)

### Add a Spatial Plot
1. Click the **`+`** tab
2. Select **Spatial Data (2D)** and click OK
3. In the new tab, click **⚙ Settings** to map channels to X, Y, Size, Color, and optionally attach a timestamp file
4. Use the sliders below and beside the plot to adjust axis ranges and time window

### Apply a Manipulation
1. Go to **Edit → Manage Manipulations** and enable the manipulations you want
2. On the **Time Series** tab: select a region, then use the **Manipulations** panel in the left sidebar to pick a channel, configure options, and click **Apply**
3. On a **Spatial** tab: the manipulation is applied to the full dataset

## Data Format Requirements

### CSV
```
timestamp,channel1,channel2,channel3
0.0,0.5,0.3,0.1
0.001,0.6,0.4,0.2
```
- First column should be timestamps (numeric)
- Non-numeric columns are loaded as string data (usable in Spatial datetime config, not plotted)

### NumPy (`.npy`)
- 2D array: shape `(n_samples, n_channels+1)`, first column = timestamps

### HDF5 (`.h5`)
- Dataset `data`: 2D array `(n_samples, n_channels+1)`
- Optional attribute: `sample_rate`

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save session |
| `Ctrl+E` | Export annotations |
| `Ctrl+Shift+O` | Load config |
| `Ctrl+Shift+S` | Save config |
| `Ctrl+Q` | Quit |

## Tips

- **Performance on large datasets**: The Time Series tab auto-downsamples to match screen pixel width and clips off-screen points — rendering stays fast even with millions of samples
- **Spatial performance**: Set a low **Max displayed rows** (e.g. 5,000–10,000) in Spatial Settings for fast interaction; the points are randomly sampled
- **STFT resolution**: larger window size → better frequency resolution; higher overlap → better time resolution
- **Window size**: no upper limit — enter any integer value
- **Multiple datasets**: load as many files as you need; each gets its own entry in Data Mgmt and its own Plot Box in Time Series

## Troubleshooting

**App doesn't start** — run `pip install -r requirements.txt`

**File won't load** — check the format requirements above; look at the error in the status bar

**Plots are empty after loading** — go to Data Mgmt, make sure channels are configured and **Apply** was clicked

**Spatial tab: time masking not working** — verify the timestamp file has the same number of rows as the spatial data; check **⚙ Settings → Configure datetime columns** if using non-numeric timestamps

