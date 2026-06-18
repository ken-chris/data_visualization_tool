# Project Summary

## Architecture

**Stack:** PyQt6 · PyQtGraph · NumPy · SciPy · Pandas

```
DataVisualizer/
├── src/
│   ├── main.py                        # Entry point
│   ├── main_window.py                 # Main window, tab management, signal wiring
│   ├── models/
│   │   ├── sensor_data.py             # SensorData + StringData models
│   │   └── annotation.py             # Annotation model
│   ├── widgets/
│   │   ├── timeseries_widget.py       # Scrollable multi-channel time series
│   │   ├── plot_box.py                # Individual channel plot box
│   │   ├── spectrogram_widget.py      # STFT heatmap viewer
│   │   ├── fft_widget.py              # FFT frequency domain viewer
│   │   ├── spatial_widget.py          # Scatter plot (2D spatial data)
│   │   ├── data_mgmt_panel.py         # Dataset/channel management
│   │   ├── parameter_panel.py         # STFT/FFT parameter controls + CollapsibleSection
│   │   ├── annotation_panel.py        # Annotation label management
│   │   ├── manipulation_panel.py      # Manipulation sidebar panel
│   │   ├── add_tab_dialog.py          # "+" tab dialog + widget registry
│   │   ├── load_dialog.py             # File load dialog with progress
│   │   └── manage_config_dialog.py    # Manipulation enable/disable dialog
│   ├── manipulations/
│   │   ├── base.py                    # DataManipulation base class + registry
│   │   ├── normalize.py               # Z-score / min-max normalization
│   │   ├── butter_filter.py           # Butterworth IIR filter
│   │   └── Cher_filter.py             # Chebyshev Type I filter
│   └── utils/
│       ├── data_loader.py             # CSV / NumPy / HDF5 loading; string column handling
│       ├── signal_processing.py       # FFT, STFT, window functions
│       ├── export.py                  # JSON/CSV annotation export; session save/load
│       └── config.py                  # AppConfig dataclass
├── requirements.txt
├── run.bat
├── generate_sample_data.py
├── README.md
├── GETTING_STARTED.md
├── CONFIG_GUIDE.md
├── ANNOTATION_GUIDE.md
└── MANIPULATIONS.md
```

## Key Design Decisions

### Tab System
- Core tabs (Time Series, Spectrogram, FFT, Data Mgmt) are statically created at startup
- The app opens on **Data Mgmt** by default
- Dynamic tabs are added via the **`+`** tab; each registered widget provides a factory function that returns `(widget, sidebar_widget, label)`
- `left_stack` (QStackedWidget) switches the sidebar content per tab

### Data Model
- `SensorData`: holds `data` (numpy array, n_samples × n_channels), `timestamps`, `channel_names`, `filename`
- `StringData`: holds non-numeric columns; not rendered in any plot, but available for datetime configuration in the Spatial widget
- Multiple datasets are stored in `MainWindow.datasets: Dict[str, SensorData]`

### Manipulations System
- `DataManipulation` subclasses self-register via `__init_subclass__` into `manipulation_registry`
- The `ManipulationPanel` widget auto-generates controls from each class's `options` dict
- On Time Series: manipulations apply to the selected region only
- On Spatial tabs: manipulations apply to the full dataset
- See [MANIPULATIONS.md](MANIPULATIONS.md) to add new manipulations

### Performance
- **Time Series**: `setClipToView(True)` + `setDownsampling(auto=True, method='peak')` per `PlotDataItem` — PyQtGraph handles LOD automatically
- **Spatial color**: 256-entry pre-built `QBrush` palette (viridis); per-point indices into the palette — avoids creating N unique brush objects
- **Spatial data**: random subsample capped at `max_rows` (default 10,000)

### Spatial Widget
- Registered in the extensible tab system via `register_tab_widget`
- Supports external timestamp files with full datetime parsing (split columns, custom separators, all Python `datetime` fields)
- X/Y range sliders zoom the plot axes (do not mask data)
- Time window slider masks data by timestamp; window size is set separately with an Apply button to avoid per-keystroke redraws

## Dependencies

| Package | Purpose |
|---------|---------|
| PyQt6 ≥ 6.6 | GUI framework |
| pyqtgraph ≥ 0.13 | Hardware-accelerated plotting |
| numpy ≥ 1.24 | Numerical arrays |
| scipy ≥ 1.11 | Signal processing (FFT, filters) |
| pandas ≥ 2.0 | CSV loading |
| h5py ≥ 3.9 | HDF5 support (optional) |

