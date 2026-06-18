"""
Spatial Data (2D) widget — scatter plot with time/x/y range sliders.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.models.sensor_data import SensorData
from src.widgets.manipulation_panel import ManipulationPanel
from src.widgets.manage_config_dialog import load_enabled_manipulations

# Datetime field choices available per column
_DT_FIELDS = ["(ignore)", "year", "month", "day", "hour", "minute", "second", "microsecond"]


def _parse_time_file(
    path: str,
    col_map: List[Optional[str]],
    col_splits: Optional[Dict[int, dict]] = None,
    delimiter: Optional[str] = None,
) -> tuple:
    """
    Parse a time file into a float array of POSIX timestamps.

    Returns (timestamps_or_None, diagnostics_dict) where diagnostics_dict has:
      - 'total': total non-blank/non-comment rows seen
      - 'parsed': rows successfully parsed
      - 'failed': count of rows that failed
      - 'sample_errors': list of (line_number, line_text, error_message) for first 5 failures
    """
    col_splits = col_splits or {}
    diag: dict = {'total': 0, 'parsed': 0, 'failed': 0, 'sample_errors': []}

    has_active = any(f and f != "(ignore)" for f in col_map)
    has_split_active = any(
        any(p and p != "(ignore)" for p in info.get("parts", []))
        for info in col_splits.values()
    )

    if not has_active and not has_split_active:
        try:
            data = np.loadtxt(path, delimiter=delimiter)
            if data.ndim > 1:
                data = data[:, 0]
            arr = data.astype(float)
            diag['total'] = diag['parsed'] = len(arr)
            return arr, diag
        except Exception as e:
            diag['sample_errors'].append((0, '', str(e)))
            return None, diag

    timestamps = []
    with open(path, "r") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            diag['total'] += 1
            sep = delimiter if delimiter else None
            cols = line.split(sep)
            kwargs: dict = {"year": 1970, "month": 1, "day": 1,
                            "hour": 0, "minute": 0, "second": 0, "microsecond": 0}
            try:
                for i, field in enumerate(col_map):
                    if not field or field == "(ignore)":
                        continue
                    if i in col_splits:
                        continue
                    if i < len(cols):
                        kwargs[field] = int(float(cols[i].strip()))

                for col_idx, split_info in col_splits.items():
                    if col_idx >= len(cols):
                        continue
                    cell = cols[col_idx].strip()
                    sep2 = split_info.get("sep", "-")
                    parts_map = split_info.get("parts", [])
                    sub_parts = cell.split(sep2)
                    for sub_idx, field in enumerate(parts_map):
                        if not field or field == "(ignore)":
                            continue
                        if sub_idx < len(sub_parts):
                            kwargs[field] = int(float(sub_parts[sub_idx].strip()))

                dt = datetime(**kwargs, tzinfo=timezone.utc)
                timestamps.append(dt.timestamp())
                diag['parsed'] += 1
            except Exception as exc:
                diag['failed'] += 1
                if len(diag['sample_errors']) < 5:
                    diag['sample_errors'].append((line_no, line[:80], str(exc)))

    result = np.array(timestamps, dtype=float) if timestamps else None
    return result, diag


class _DatetimeColDialog(QDialog):
    """
    Assign datetime fields to columns in a time file.

    Each column can either:
      - Have a single field dropdown (e.g. whole column = "year"), OR
      - Have a "Split by" separator entered, which expands the cell value into
        sub-parts each with their own field dropdown (e.g. "2018-01-03" → year/month/day).
    """

    def __init__(
        self,
        path: str,
        current_col_map: List[Optional[str]],
        current_col_splits: Optional[Dict[int, dict]] = None,
        delimiter: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Configure Datetime Columns")
        self.resize(540, 320)

        self._path = path
        self._delimiter = delimiter
        self._current_col_splits: Dict[int, dict] = current_col_splits or {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"File: {os.path.basename(path)}"))
        layout.addWidget(QLabel(
            "For each column: assign a datetime field directly, or enter a split "
            "separator (e.g. '-') to expand the value into sub-parts."
        ))

        # Read first data row for preview
        self._first_row: List[str] = []
        try:
            with open(path, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self._first_row = line.split(delimiter if delimiter else None)
                        break
        except Exception:
            pass

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._inner = QWidget()
        self._grid = QHBoxLayout(self._inner)
        self._grid.setSpacing(12)

        # Per-column state: list of dicts with widget refs
        self._col_widgets: List[dict] = []

        for col_idx, raw_val in enumerate(self._first_row):
            saved_split = self._current_col_splits.get(col_idx)
            saved_direct = (
                current_col_map[col_idx]
                if col_idx < len(current_col_map)
                else None
            )
            cw = self._build_col_widget(col_idx, raw_val, saved_direct, saved_split)
            self._col_widgets.append(cw)
            self._grid.addWidget(cw["root"])

        self._grid.addStretch()
        self._scroll.setWidget(self._inner)
        layout.addWidget(self._scroll, stretch=1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _build_col_widget(
        self,
        col_idx: int,
        raw_val: str,
        saved_direct: Optional[str],
        saved_split: Optional[dict],
    ) -> dict:
        root = QWidget()
        vbox = QVBoxLayout(root)
        vbox.setSpacing(3)
        vbox.setContentsMargins(0, 0, 0, 0)

        vbox.addWidget(QLabel(f"Col {col_idx}"))
        preview_lbl = QLabel(raw_val[:16])
        preview_lbl.setStyleSheet("color: #555; font-size: 10px;")
        vbox.addWidget(preview_lbl)

        # Direct field combo
        direct_combo = QComboBox()
        for f in _DT_FIELDS:
            direct_combo.addItem(f)
        if saved_direct and saved_direct in _DT_FIELDS:
            direct_combo.setCurrentText(saved_direct)
        vbox.addWidget(direct_combo)

        # Split row
        split_row = QWidget()
        split_h = QHBoxLayout(split_row)
        split_h.setContentsMargins(0, 0, 0, 0)
        split_h.setSpacing(4)
        split_h.addWidget(QLabel("Split:"))
        sep_edit = QLineEdit()
        sep_edit.setPlaceholderText("sep")
        sep_edit.setMaximumWidth(40)
        if saved_split:
            sep_edit.setText(saved_split.get("sep", ""))
        apply_btn = QPushButton("↵")
        apply_btn.setFixedWidth(24)
        apply_btn.setToolTip("Apply split and show sub-fields")
        split_h.addWidget(sep_edit)
        split_h.addWidget(apply_btn)
        vbox.addWidget(split_row)

        # Sub-parts container (shown when split is active)
        parts_container = QWidget()
        parts_vbox = QVBoxLayout(parts_container)
        parts_vbox.setContentsMargins(0, 0, 0, 0)
        parts_vbox.setSpacing(2)
        vbox.addWidget(parts_container)

        entry = {
            "root": root,
            "direct_combo": direct_combo,
            "sep_edit": sep_edit,
            "parts_container": parts_container,
            "parts_vbox": parts_vbox,
            "part_combos": [],
            "col_idx": col_idx,
            "raw_val": raw_val,
        }

        # Connect apply button
        apply_btn.clicked.connect(
            lambda _=False, e=entry: self._apply_split(e)
        )
        sep_edit.returnPressed.connect(
            lambda e=entry: self._apply_split(e)
        )

        # Restore saved split state
        if saved_split and saved_split.get("sep"):
            self._apply_split(entry, saved_parts=saved_split.get("parts", []))

        return entry

    def _apply_split(self, entry: dict, saved_parts: Optional[List[str]] = None):
        """Re-render sub-part dropdowns based on current separator."""
        sep = entry["sep_edit"].text().strip()
        raw = entry["raw_val"]

        # Clear existing sub-part combos
        for combo in entry["part_combos"]:
            combo.setParent(None)
        entry["part_combos"].clear()

        if not sep:
            entry["direct_combo"].setEnabled(True)
            return

        sub_parts = raw.split(sep)
        entry["direct_combo"].setEnabled(False)
        entry["direct_combo"].setCurrentText("(ignore)")

        for sub_idx, sub_val in enumerate(sub_parts):
            row_w = QWidget()
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(f"[{sub_idx}] {sub_val[:8]}")
            lbl.setStyleSheet("font-size: 10px;")
            row_h.addWidget(lbl)
            combo = QComboBox()
            for f in _DT_FIELDS:
                combo.addItem(f)
            if saved_parts and sub_idx < len(saved_parts) and saved_parts[sub_idx] in _DT_FIELDS:
                combo.setCurrentText(saved_parts[sub_idx])
            row_h.addWidget(combo)
            entry["parts_vbox"].addWidget(row_w)
            entry["part_combos"].append(combo)

    def get_col_map(self) -> List[Optional[str]]:
        """Return direct field assignment per top-level column (used when no split)."""
        result = []
        for entry in self._col_widgets:
            if entry["sep_edit"].text().strip():
                result.append("(ignore)")
            else:
                result.append(entry["direct_combo"].currentText())
        return result

    def get_col_splits(self) -> Dict[int, dict]:
        """Return per-column split configs for columns using a separator."""
        result: Dict[int, dict] = {}
        for entry in self._col_widgets:
            sep = entry["sep_edit"].text().strip()
            if not sep or not entry["part_combos"]:
                continue
            parts = [c.currentText() for c in entry["part_combos"]]
            result[entry["col_idx"]] = {"sep": sep, "parts": parts}
        return result


class SpatialSettingsDialog(QDialog):
    """Configure channel mappings and optional time file for the scatter plot."""

    def __init__(
        self,
        channel_names: list[str],
        current: Optional[dict] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Spatial Data (2D) Settings")
        self.resize(420, 380)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        def _combo(include_none: bool = False) -> QComboBox:
            combo = QComboBox()
            if include_none:
                combo.addItem("(none)")
            for name in channel_names:
                combo.addItem(name)
            return combo

        self.x_combo = _combo()
        self.y_combo = _combo()
        self.size_combo = _combo(include_none=True)
        self.color_combo = _combo(include_none=True)

        form.addRow("X channel:", self.x_combo)
        form.addRow("Y channel:", self.y_combo)
        form.addRow("Size channel (opt):", self.size_combo)
        form.addRow("Color channel (opt):", self.color_combo)

        self.max_rows_spin = QSpinBox()
        self.max_rows_spin.setMinimum(100)
        self.max_rows_spin.setMaximum(10_000_000)
        self.max_rows_spin.setSingleStep(1000)
        self.max_rows_spin.setValue(10_000)
        self.max_rows_spin.setToolTip(
            "Maximum rows to display (random subsample if data exceeds this). "
            "Lower = faster rendering."
        )
        form.addRow("Max displayed rows:", self.max_rows_spin)
        layout.addLayout(form)

        time_group = QGroupBox("Time")
        time_layout = QVBoxLayout(time_group)

        file_row = QHBoxLayout()
        self.time_label = QLabel("(none)")
        self.time_label.setWordWrap(True)
        self._time_path: Optional[str] = None
        self._time_col_map: List[Optional[str]] = []
        self._time_col_splits: Dict[int, dict] = {}
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_time)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_time)
        file_row.addWidget(self.time_label, stretch=1)
        file_row.addWidget(browse_btn)
        file_row.addWidget(clear_btn)
        time_layout.addLayout(file_row)

        self._dt_btn = QPushButton("Configure datetime columns…")
        self._dt_btn.setEnabled(False)
        self._dt_btn.clicked.connect(self._configure_datetime)
        time_layout.addWidget(self._dt_btn)
        layout.addWidget(time_group)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        if current:
            self._restore(current)

    def _browse_time(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select timestamp file", "",
            "CSV / Text Files (*.csv *.txt *.tsv);;All Files (*)",
        )
        if path:
            self._time_path = path
            self._time_col_map = []
            self._time_col_splits = {}
            self.time_label.setText(os.path.basename(path))
            self._dt_btn.setEnabled(True)

    def _clear_time(self):
        self._time_path = None
        self._time_col_map = []
        self._time_col_splits = {}
        self.time_label.setText("(none)")
        self._dt_btn.setEnabled(False)

    def _configure_datetime(self):
        if not self._time_path:
            return
        dlg = _DatetimeColDialog(
            self._time_path,
            self._time_col_map,
            current_col_splits=self._time_col_splits,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._time_col_map = dlg.get_col_map()
            self._time_col_splits = dlg.get_col_splits()

    def _combo_set(self, combo: QComboBox, name: Optional[str]):
        if name is None:
            combo.setCurrentIndex(0)
            return
        idx = combo.findText(name)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _restore(self, cfg: dict):
        self._combo_set(self.x_combo, cfg.get('x'))
        self._combo_set(self.y_combo, cfg.get('y'))
        self._combo_set(self.size_combo, cfg.get('size'))
        self._combo_set(self.color_combo, cfg.get('color'))
        self.max_rows_spin.setValue(cfg.get('max_rows', 10_000))
        if cfg.get('time_path'):
            self._time_path = cfg['time_path']
            self._time_col_map = cfg.get('time_col_map', [])
            self._time_col_splits = {
                int(k): v for k, v in cfg.get('time_col_splits', {}).items()
            }
            self.time_label.setText(os.path.basename(self._time_path))
            self._dt_btn.setEnabled(True)

    def _get_optional(self, combo: QComboBox) -> Optional[str]:
        value = combo.currentText()
        return None if value == "(none)" else value

    def get_config(self) -> dict:
        return {
            'x': self.x_combo.currentText(),
            'y': self.y_combo.currentText(),
            'size': self._get_optional(self.size_combo),
            'color': self._get_optional(self.color_combo),
            'max_rows': self.max_rows_spin.value(),
            'time_path': self._time_path,
            'time_col_map': self._time_col_map,
            'time_col_splits': self._time_col_splits,
        }


class _RangeSlider(QWidget):
    """A simple two-handle range slider using two QSliders overlaid."""

    range_changed = pyqtSignal(float, float)
    _STEPS = 1000

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(parent)

        if orientation == Qt.Orientation.Horizontal:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._lo = QSlider(Qt.Orientation.Horizontal)
            self._hi = QSlider(Qt.Orientation.Horizontal)
            self._lo.setMaximumHeight(12)
            self._hi.setMaximumHeight(12)
        else:
            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._lo = QSlider(Qt.Orientation.Vertical)
            self._hi = QSlider(Qt.Orientation.Vertical)
            self._lo.setMaximumWidth(12)
            self._hi.setMaximumWidth(12)

        for slider in (self._lo, self._hi):
            slider.setMinimum(0)
            slider.setMaximum(self._STEPS)
        self._lo.setValue(0)
        self._hi.setValue(self._STEPS)

        layout.addWidget(self._lo)
        layout.addWidget(self._hi)

        self._lo.valueChanged.connect(self._on_lo)
        self._hi.valueChanged.connect(self._on_hi)

    def _emit_range(self):
        self.range_changed.emit(
            self._lo.value() / self._STEPS,
            self._hi.value() / self._STEPS,
        )

    def _on_lo(self, value):
        if value > self._hi.value():
            self._lo.setValue(self._hi.value())
            return
        self._emit_range()

    def _on_hi(self, value):
        if value < self._lo.value():
            self._hi.setValue(self._lo.value())
            return
        self._emit_range()

    def set_range(self, lo_frac: float, hi_frac: float):
        self._lo.blockSignals(True)
        self._hi.blockSignals(True)
        self._lo.setValue(int(lo_frac * self._STEPS))
        self._hi.setValue(int(hi_frac * self._STEPS))
        self._lo.blockSignals(False)
        self._hi.blockSignals(False)

    def get_range(self) -> tuple[float, float]:
        return self._lo.value() / self._STEPS, self._hi.value() / self._STEPS


class SpatialWidget(QWidget):
    """Scatter plot widget for spatial (2D) data visualization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._datasets: Dict[str, SensorData] = {}
        self._config: dict = {}
        self._scatter: Optional[pg.ScatterPlotItem] = None
        self._x_data: Optional[np.ndarray] = None
        self._y_data: Optional[np.ndarray] = None
        self._size_data: Optional[np.ndarray] = None
        self._time_data: Optional[np.ndarray] = None
        self._time_is_datetime: bool = False
        self._size_arr: Optional[np.ndarray] = None    # pre-computed, shape (N,) float
        self._color_arr: Optional[np.ndarray] = None   # pre-computed palette indices, shape (N,) int
        self._color_palette: list = []                  # 256 pre-built QBrush objects

        # Manipulation sidebar — owned by this widget, returned as sidebar from factory
        self.manip_panel = ManipulationPanel()
        enabled = load_enabled_manipulations()
        self.manip_panel.set_enabled(enabled)

        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        toolbar = QHBoxLayout()
        self._dataset_combo = QComboBox()
        self._dataset_combo.currentIndexChanged.connect(self._on_dataset_changed)
        toolbar.addWidget(QLabel("Dataset:"))
        toolbar.addWidget(self._dataset_combo)
        toolbar.addStretch()
        self._settings_btn = QPushButton("⚙ Settings")
        self._settings_btn.clicked.connect(self._open_settings)
        toolbar.addWidget(self._settings_btn)
        outer.addLayout(toolbar)

        plot_row = QHBoxLayout()
        plot_row.setSpacing(4)

        y_slider_col = QVBoxLayout()
        y_slider_col.setSpacing(2)
        self._y_hi_label = QLabel("max")
        self._y_hi_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._y_lo_label = QLabel("min")
        self._y_lo_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._y_range_slider = _RangeSlider(Qt.Orientation.Vertical)
        self._y_range_slider.set_range(0.0, 1.0)
        self._y_range_slider.range_changed.connect(self._on_y_range)
        y_slider_col.addWidget(self._y_hi_label)
        y_slider_col.addWidget(self._y_range_slider, stretch=1)
        y_slider_col.addWidget(self._y_lo_label)
        plot_row.addLayout(y_slider_col)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground('w')
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.setLabel('bottom', 'X')
        self._plot_widget.setLabel('left', 'Y')
        self._scatter = pg.ScatterPlotItem(size=8, pen=None)
        self._plot_widget.addItem(self._scatter)
        plot_row.addWidget(self._plot_widget, stretch=1)
        outer.addLayout(plot_row, stretch=1)

        x_range_row = QHBoxLayout()
        x_range_row.setSpacing(2)
        self._x_lo_label = QLabel("min")
        self._x_hi_label = QLabel("max")
        self._x_range_slider = _RangeSlider(Qt.Orientation.Horizontal)
        self._x_range_slider.set_range(0.0, 1.0)
        self._x_range_slider.range_changed.connect(self._on_x_range)
        x_range_row.addWidget(self._x_lo_label)
        x_range_row.addWidget(self._x_range_slider, stretch=1)
        x_range_row.addWidget(self._x_hi_label)
        outer.addLayout(x_range_row)

        self._time_group = QWidget()
        time_layout = QHBoxLayout(self._time_group)
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setSpacing(4)
        time_layout.addWidget(QLabel("Time window:"))
        self._time_slider = QSlider(Qt.Orientation.Horizontal)
        self._time_slider.setMinimum(0)
        self._time_slider.setMaximum(1000)
        self._time_slider.setValue(0)
        self._time_slider.valueChanged.connect(self._on_time_slider)
        time_layout.addWidget(self._time_slider, stretch=1)
        time_layout.addWidget(QLabel("Window (s):"))
        self._time_window_spin = QDoubleSpinBox()
        self._time_window_spin.setSuffix(" s")
        self._time_window_spin.setMinimum(0.001)
        self._time_window_spin.setMaximum(1e9)
        self._time_window_spin.setValue(1.0)
        # Do NOT connect valueChanged — user must click Apply
        time_layout.addWidget(self._time_window_spin)
        self._time_apply_btn = QPushButton("Apply")
        self._time_apply_btn.setFixedWidth(52)
        self._time_apply_btn.clicked.connect(self._on_time_slider)
        time_layout.addWidget(self._time_apply_btn)
        self._time_pos_label = QLabel("—")
        time_layout.addWidget(self._time_pos_label)
        self._time_group.setVisible(False)
        outer.addWidget(self._time_group)

    def refresh_manip_channels(self, datasets: Dict[str, SensorData]):
        """Rebuild the manipulation panel's channel list from the given datasets."""
        channel_info = []
        for dataset_id, sd in datasets.items():
            for ch_idx, ch_name in enumerate(sd.channel_names):
                channel_info.append((dataset_id, ch_idx, ch_name))
        self.manip_panel.refresh_channels(channel_info)

    def set_datasets(self, datasets: Dict[str, SensorData]):
        """Update available datasets for plotting."""
        self._datasets = datasets
        current = self._dataset_combo.currentText()
        self._dataset_combo.blockSignals(True)
        self._dataset_combo.clear()
        for name in datasets:
            self._dataset_combo.addItem(name)
        idx = self._dataset_combo.findText(current)
        if idx < 0 and self._dataset_combo.count() > 0:
            idx = 0
        self._dataset_combo.setCurrentIndex(idx)
        self._dataset_combo.blockSignals(False)

        if self._config and self._dataset_combo.count() > 0:
            self._load_data()
        elif self._dataset_combo.count() == 0 and self._scatter is not None:
            self._scatter.setData(x=[], y=[])

    def _current_sensor_data(self) -> Optional[SensorData]:
        return self._datasets.get(self._dataset_combo.currentText())

    def _on_dataset_changed(self):
        if self._config:
            self._load_data()

    def _open_settings(self):
        sd = self._current_sensor_data()
        if sd is None:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "No data", "Load data first.")
            return

        dlg = SpatialSettingsDialog(list(sd.channel_names), current=self._config, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._config = dlg.get_config()
            self._load_data()

    def _ch_idx(self, sd: SensorData, name: Optional[str]) -> Optional[int]:
        if name is None:
            return None
        try:
            return list(sd.channel_names).index(name)
        except ValueError:
            return None

    def _load_data(self):
        sd = self._current_sensor_data()
        if sd is None or not self._config:
            return

        x_idx = self._ch_idx(sd, self._config.get('x'))
        y_idx = self._ch_idx(sd, self._config.get('y'))
        if x_idx is None or y_idx is None:
            return

        self._x_data = sd.data[:, x_idx].astype(float)
        self._y_data = sd.data[:, y_idx].astype(float)

        size_idx = self._ch_idx(sd, self._config.get('size'))
        self._size_data = sd.data[:, size_idx].astype(float) if size_idx is not None else None

        time_path = self._config.get('time_path')
        if time_path and os.path.exists(time_path):
            col_map = self._config.get('time_col_map', [])
            col_splits = {
                int(k): v for k, v in self._config.get('time_col_splits', {}).items()
            }
            has_dt_fields = any(f and f != "(ignore)" for f in col_map) or bool(col_splits)
            parsed, diag = _parse_time_file(time_path, col_map, col_splits=col_splits)

            if diag['failed'] > 0:
                sample = "\n".join(
                    f"  Line {ln}: {txt!r} → {err}"
                    for ln, txt, err in diag['sample_errors']
                )
                QMessageBox.warning(
                    self, "Datetime parse failed",
                    f"{diag['failed']:,} of {diag['total']:,} rows failed to parse.\n"
                    "Timestamps discarded to avoid misalignment.\n\n"
                    f"First failures:\n{sample}\n\n"
                    "Fix the config in '⚙ Settings → Configure datetime columns…'."
                )
                self._time_data = None
                self._time_is_datetime = False
            else:
                self._time_data = parsed
                self._time_is_datetime = has_dt_fields and self._time_data is not None
        else:
            self._time_data = sd.timestamps if sd.timestamps is not None else None
            self._time_is_datetime = False

        n_full = len(self._x_data)

        if self._time_data is not None and len(self._time_data) != n_full:
            QMessageBox.warning(
                self, "Time data length mismatch",
                f"Time file produced {len(self._time_data):,} timestamps but spatial data has "
                f"{n_full:,} rows. Time masking will be disabled.",
            )
            self._time_data = None

        # ── Apply max-rows subsample (random, reproducible) ──────────────
        max_rows = self._config.get('max_rows', 10_000)
        subsample_idx = None
        if n_full > max_rows:
            rng = np.random.default_rng(42)
            subsample_idx = np.sort(rng.choice(n_full, size=max_rows, replace=False))
            self._x_data = self._x_data[subsample_idx]
            self._y_data = self._y_data[subsample_idx]
            if self._size_data is not None:
                self._size_data = self._size_data[subsample_idx]
            if self._time_data is not None:
                self._time_data = self._time_data[subsample_idx]

        n = len(self._x_data)

        # Pre-compute size array (normalised to 4–24px)
        if self._size_data is not None and len(self._size_data) == n:
            s_min = float(np.nanmin(self._size_data))
            s_max = float(np.nanmax(self._size_data))
            s_span = s_max - s_min or 1.0
            self._size_arr = (4 + 20 * (self._size_data - s_min) / s_span).astype(float)
        else:
            self._size_arr = None

        # Pre-compute colour palette indices (256 levels → viridis colormap)
        color_ch_idx = self._ch_idx(sd, self._config.get('color'))
        if color_ch_idx is not None:
            color_raw = sd.data[:, color_ch_idx].astype(float)
            if subsample_idx is not None:
                color_raw = color_raw[subsample_idx]
        else:
            color_raw = None

        if color_raw is not None and len(color_raw) == n:
            c_min = float(np.nanmin(color_raw))
            c_max = float(np.nanmax(color_raw))
            c_span = c_max - c_min or 1.0
            _N = 256
            cmap = pg.colormap.get('viridis')
            self._color_palette = [
                pg.mkBrush(int(cmap.map(i / (_N - 1))[0]),
                           int(cmap.map(i / (_N - 1))[1]),
                           int(cmap.map(i / (_N - 1))[2]),
                           200)
                for i in range(_N)
            ]
            self._color_arr = ((color_raw - c_min) / c_span * (_N - 1)).clip(0, _N - 1).astype(int)
        else:
            self._color_arr = None
            self._color_palette = []

        self._plot_widget.setLabel('bottom', self._config.get('x', 'X'))
        self._plot_widget.setLabel('left', self._config.get('y', 'Y'))

        x_min, x_max = float(np.nanmin(self._x_data)), float(np.nanmax(self._x_data))
        y_min, y_max = float(np.nanmin(self._y_data)), float(np.nanmax(self._y_data))
        self._x_lo_label.setText(f"{x_min:.3g}")
        self._x_hi_label.setText(f"{x_max:.3g}")
        self._y_lo_label.setText(f"{y_min:.3g}")
        self._y_hi_label.setText(f"{y_max:.3g}")
        self._x_range_slider.set_range(0.0, 1.0)
        self._y_range_slider.set_range(0.0, 1.0)

        has_time = self._time_data is not None and len(self._time_data) > 0
        self._time_group.setVisible(has_time)
        if has_time:
            t_min, t_max = float(np.nanmin(self._time_data)), float(np.nanmax(self._time_data))
            duration = max(t_max - t_min, 1e-9)
            self._time_window_spin.blockSignals(True)
            self._time_window_spin.setMaximum(duration)
            self._time_window_spin.setValue(duration * 0.05)
            self._time_window_spin.blockSignals(False)

        self._on_time_slider()

    def _build_mask(self) -> np.ndarray:
        """Build boolean mask for time filter. X/Y ranges are handled via setXRange/setYRange."""
        n_points = len(self._x_data)

        if self._time_data is None:
            return np.ones(n_points, dtype=bool)

        t_min = float(np.nanmin(self._time_data))
        t_max = float(np.nanmax(self._time_data))
        t_span = t_max - t_min or 1.0
        t_frac = self._time_slider.value() / max(self._time_slider.maximum(), 1)
        t_center = t_min + t_frac * t_span
        window = self._time_window_spin.value()
        return (
            (self._time_data >= t_center - window / 2.0) &
            (self._time_data <= t_center + window / 2.0)
        )

    def _refresh_plot(self):
        if self._x_data is None or self._y_data is None or self._scatter is None:
            return

        mask = self._build_mask()
        x = self._x_data[mask]
        y = self._y_data[mask]

        sizes = self._size_arr[mask] if self._size_arr is not None else 8

        if self._color_arr is not None and self._color_palette:
            # Reuse pre-built palette brushes — only 256 unique QBrush objects
            indices = self._color_arr[mask]
            brushes = [self._color_palette[i] for i in indices]
        else:
            brushes = pg.mkBrush(31, 119, 180, 180)

        self._scatter.setData(x=x, y=y, size=sizes, brush=brushes, pen=None)

    def _on_x_range(self, lo_frac: float, hi_frac: float):
        """Zoom the plot X axis to the slider range."""
        if self._x_data is None:
            return
        x_min = float(np.nanmin(self._x_data))
        x_max = float(np.nanmax(self._x_data))
        x_span = x_max - x_min or 1.0
        self._plot_widget.setXRange(
            x_min + lo_frac * x_span,
            x_min + hi_frac * x_span,
            padding=0,
        )

    def _on_y_range(self, lo_frac: float, hi_frac: float):
        """Zoom the plot Y axis to the slider range."""
        if self._y_data is None:
            return
        y_min = float(np.nanmin(self._y_data))
        y_max = float(np.nanmax(self._y_data))
        y_span = y_max - y_min or 1.0
        self._plot_widget.setYRange(
            y_min + lo_frac * y_span,
            y_min + hi_frac * y_span,
            padding=0,
        )

    def _on_time_slider(self, *_args):
        if self._time_data is not None and len(self._time_data) > 0:
            t_min = float(np.nanmin(self._time_data))
            t_max = float(np.nanmax(self._time_data))
            t_span = t_max - t_min or 1.0
            t_frac = self._time_slider.value() / max(self._time_slider.maximum(), 1)
            t_pos = t_min + t_frac * t_span
            if self._time_is_datetime:
                try:
                    dt = datetime.fromtimestamp(t_pos, tz=timezone.utc)
                    # Show as much precision as the data warrants
                    if dt.second or dt.microsecond:
                        label = dt.strftime("%Y-%m-%d %H:%M:%S")
                    elif dt.hour or dt.minute:
                        label = dt.strftime("%Y-%m-%d %H:%M")
                    else:
                        label = dt.strftime("%Y-%m-%d")
                    self._time_pos_label.setText(label)
                except (OSError, OverflowError, ValueError):
                    self._time_pos_label.setText(f"t={t_pos:.2f}")
            else:
                self._time_pos_label.setText(f"t={t_pos:.4g}")
        else:
            self._time_pos_label.setText("—")
        self._refresh_plot()


def _spatial_factory():
    widget = SpatialWidget()
    return widget, widget.manip_panel, "Spatial 2D"


try:
    from src.widgets.add_tab_dialog import register_tab_widget

    register_tab_widget(
        "Spatial Data (2D)",
        "2D scatter plot with X/Y/size/color channel mapping and time windowing",
        _spatial_factory,
    )
except ImportError:
    pass
