"""
Data loading utilities for various file formats.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, List
from src.models.sensor_data import SensorData
from src.models.annotation import Annotation


def load_csv(filepath: str) -> SensorData:
    """
    Load sensor data from CSV file.

    Expected format:
        - First column: timestamps
        - Remaining columns: sensor channels (numeric) or string data
        - Header row with column names (optional)

    Non-numeric columns are stored in SensorData.string_columns and are NOT
    rendered by any visualization tab. They are available for future use in
    manipulations or custom widgets.

    Args:
        filepath: Path to CSV file

    Returns:
        SensorData object
    """
    df = pd.read_csv(filepath)

    # First column is timestamp — try to coerce to float
    ts_col = df.iloc[:, 0]
    try:
        timestamps = pd.to_numeric(ts_col, errors='raise').values.astype(float)
    except (ValueError, TypeError):
        # Fallback: integer row index as time axis
        timestamps = np.arange(len(df), dtype=float)

    # Separate numeric vs non-numeric data columns
    data_df = df.iloc[:, 1:]
    numeric_cols: List[str] = []
    numeric_arrays: List[np.ndarray] = []
    string_columns: Dict[str, np.ndarray] = {}

    for col in data_df.columns:
        coerced = pd.to_numeric(data_df[col], errors='coerce')
        if coerced.isna().all():
            # Entirely non-numeric — store as strings
            string_columns[col] = data_df[col].astype(str).values
        else:
            numeric_cols.append(col)
            numeric_arrays.append(coerced.values.astype(float))

    if numeric_arrays:
        data = np.column_stack(numeric_arrays)
    else:
        # No numeric channels — create empty data with correct row count
        data = np.empty((len(timestamps), 0), dtype=float)

    # Infer sample rate from timestamps
    if len(timestamps) > 1:
        dt = np.diff(timestamps).mean()
        sample_rate = 1.0 / dt if dt != 0 else 1.0
    else:
        sample_rate = 1.0

    return SensorData(
        timestamps=timestamps,
        data=data,
        sample_rate=sample_rate,
        channel_names=numeric_cols,
        filename=Path(filepath).name,
        string_columns=string_columns,
    )


def load_numpy(filepath: str) -> SensorData:
    """
    Load sensor data from NumPy binary file (.npy).
    
    Expected format:
        - 2D array with shape (n_samples, n_channels+1)
        - First column: timestamps
        - Remaining columns: sensor channels
    
    Args:
        filepath: Path to .npy file
        
    Returns:
        SensorData object
    """
    arr = np.load(filepath)
    
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D array, got shape {arr.shape}")
    
    timestamps = arr[:, 0]
    data = arr[:, 1:]
    
    # Infer sample rate
    if len(timestamps) > 1:
        dt = np.diff(timestamps).mean()
        sample_rate = 1.0 / dt
    else:
        sample_rate = 1.0
    
    return SensorData(
        timestamps=timestamps,
        data=data,
        sample_rate=sample_rate,
        filename=Path(filepath).name
    )


def load_hdf5(filepath: str, dataset_name: str = 'data') -> SensorData:
    """
    Load sensor data from HDF5 file.
    
    Expected format:
        - Dataset with name specified by dataset_name
        - 2D array with shape (n_samples, n_channels+1)
        - First column: timestamps
        - Optional attribute 'sample_rate'
        - Optional attribute 'channel_names'
    
    Args:
        filepath: Path to HDF5 file
        dataset_name: Name of dataset in HDF5 file
        
    Returns:
        SensorData object
    """
    try:
        import h5py
    except ImportError:
        raise ImportError("h5py is required to load HDF5 files. Install with: pip install h5py")
    
    with h5py.File(filepath, 'r') as f:
        if dataset_name not in f:
            raise ValueError(f"Dataset '{dataset_name}' not found in HDF5 file")
        
        arr = f[dataset_name][:]
        
        if arr.ndim != 2:
            raise ValueError(f"Expected 2D array, got shape {arr.shape}")
        
        timestamps = arr[:, 0]
        data = arr[:, 1:]
        
        # Try to get sample rate from attributes
        if 'sample_rate' in f[dataset_name].attrs:
            sample_rate = float(f[dataset_name].attrs['sample_rate'])
        else:
            # Infer from timestamps
            if len(timestamps) > 1:
                dt = np.diff(timestamps).mean()
                sample_rate = 1.0 / dt
            else:
                sample_rate = 1.0
        
        # Try to get channel names from attributes
        channel_names = None
        if 'channel_names' in f[dataset_name].attrs:
            channel_names = list(f[dataset_name].attrs['channel_names'])
    
    return SensorData(
        timestamps=timestamps,
        data=data,
        sample_rate=sample_rate,
        channel_names=channel_names,
        filename=Path(filepath).name
    )


def load_annotations_json(filepath: str) -> List[Annotation]:
    """
    Load annotations from JSON file.
    
    Supports flexible JSON format - only requires 'label', 'start_time', and 'end_time'
    for each annotation. Optional fields include 'color', 'notes', 'duration', and 'sample_rate'.
    
    Expected format:
        - Can be a direct array of annotation objects: [{...}, {...}]
        - Or an object with 'annotations' key: {"annotations": [{...}, {...}]}
        - Or an object with 'annotations' key and other metadata
    
    Minimal example:
        [
            {"label": "Event1", "start_time": 1.0, "end_time": 2.5},
            {"label": "Event2", "start_time": 5.0, "end_time": 7.2}
        ]
    
    Full example with optional fields:
        {
            "sensor_file": "data.npy",
            "annotations": [
                {
                    "label": "Label1",
                    "start_time": 1.5,
                    "end_time": 3.2,
                    "color": [255, 0, 0],
                    "notes": "Some notes",
                    "duration": 1.7,
                    "sample_rate": 100.0
                }
            ]
        }
    
    Args:
        filepath: Path to JSON file containing annotations
        
    Returns:
        List of Annotation objects
        
    Raises:
        ValueError: If required fields are missing
        FileNotFoundError: If file does not exist
    """
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    # Handle both direct array and object with 'annotations' key
    annotations_list = data if isinstance(data, list) else data.get('annotations', [])
    
    if not isinstance(annotations_list, list):
        raise ValueError("Expected 'annotations' to be a list")
    
    annotations = []
    for idx, ann_data in enumerate(annotations_list):
        # Validate required fields
        required_fields = ['label', 'start_time', 'end_time']
        missing_fields = [field for field in required_fields if field not in ann_data]
        
        if missing_fields:
            raise ValueError(
                f"Annotation {idx} is missing required fields: {', '.join(missing_fields)}. "
                f"Each annotation must have 'label', 'start_time', and 'end_time'."
            )
        
        annotations.append(Annotation.from_dict(ann_data))
    
    return annotations


def load_data(filepath: str) -> SensorData:
    """
    Auto-detect file format and load sensor data.
    
    Args:
        filepath: Path to data file
        
    Returns:
        SensorData object
        
    Raises:
        ValueError: If file format is not supported
    """
    path = Path(filepath)
    suffix = path.suffix.lower()
    
    if suffix == '.csv':
        return load_csv(filepath)
    elif suffix == '.npy':
        return load_numpy(filepath)
    elif suffix in ['.h5', '.hdf5']:
        return load_hdf5(filepath)
    else:
        raise ValueError(f"Unsupported file format: {suffix}. "
                        f"Supported formats: .csv, .npy, .h5, .hdf5")
