"""
Parameter control panels for STFT and FFT configuration.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSpinBox,
    QSlider, QComboBox, QPushButton, QFormLayout, QCheckBox,
    QDoubleSpinBox, QSizePolicy, QToolButton
)
from PyQt6.QtCore import pyqtSignal, Qt
from typing import Optional


class ResizeHandle(QWidget):
    """Thin draggable bar that resizes a target widget vertically when dragged."""

    def __init__(self, target: QWidget, parent=None):
        super().__init__(parent)
        self._target = target
        self._drag_start_y: Optional[float] = None
        self._drag_start_height: Optional[int] = None
        self.setFixedHeight(7)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setStyleSheet(
            "background: #cccccc; border-radius: 3px; margin: 1px 0;"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_y = event.globalPosition().y()
            self._drag_start_height = self._target.height()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_start_y is not None:
            delta = int(event.globalPosition().y() - self._drag_start_y)
            new_h = max(60, self._drag_start_height + delta)
            self._target.setFixedHeight(new_h)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_y = None
            self._drag_start_height = None
            event.accept()


class CollapsibleSection(QWidget):
    """A titled section that can be expanded or collapsed by clicking its header."""

    def __init__(self, title: str, parent=None, expanded: bool = True):
        super().__init__(parent)
        self._expanded = expanded

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header button
        self._toggle_btn = QToolButton()
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(expanded)
        self._toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle_btn.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self._toggle_btn.setText(f"  {title}")
        self._toggle_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._toggle_btn.setStyleSheet(
            "QToolButton { border: none; background: #d8d8d8; padding: 4px; font-weight: bold; }"
            "QToolButton:hover { background: #c8c8c8; }"
        )
        font = self._toggle_btn.font()
        font.setPointSize(9)
        self._toggle_btn.setFont(font)
        self._toggle_btn.clicked.connect(self._on_toggle)
        outer.addWidget(self._toggle_btn)

        # Content container
        self._content = QWidget()
        self._content.setVisible(expanded)
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(4)
        self._content_layout = content_layout
        outer.addWidget(self._content)

    def _on_toggle(self):
        self._expanded = self._toggle_btn.isChecked()
        self._toggle_btn.setArrowType(
            Qt.ArrowType.DownArrow if self._expanded else Qt.ArrowType.RightArrow
        )
        self._content.setVisible(self._expanded)

    def add_widget(self, widget: QWidget):
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        self._content_layout.addLayout(layout)


class STFTParameterPanel(QWidget):
    """Panel for controlling STFT parameters and dB scale settings."""

    stft_parameters_changed = pyqtSignal(int, float, str, bool, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)

        # --- STFT Parameters & dB Scale (single collapsible section) ---
        stft_section = CollapsibleSection("STFT Parameters & dB Scale")
        stft_layout = QFormLayout()
        stft_layout.setContentsMargins(0, 0, 0, 0)

        self.window_size_spin = QSpinBox()
        self.window_size_spin.setMinimum(64)
        self.window_size_spin.setMaximum(2_147_483_647)
        self.window_size_spin.setValue(256)
        self.window_size_spin.setSingleStep(64)
        self.window_size_spin.setToolTip("FFT window size in samples")
        stft_layout.addRow("Window Size:", self.window_size_spin)

        overlap_layout = QVBoxLayout()
        self.overlap_slider = QSlider(Qt.Orientation.Horizontal)
        self.overlap_slider.setMinimum(0)
        self.overlap_slider.setMaximum(90)
        self.overlap_slider.setValue(50)
        self.overlap_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.overlap_slider.setTickInterval(10)
        self.overlap_slider.setToolTip("Window overlap percentage")

        self.overlap_label = QLabel("50%")
        self.overlap_slider.valueChanged.connect(
            lambda val: self.overlap_label.setText(f"{val}%")
        )

        overlap_layout.addWidget(self.overlap_slider)
        overlap_layout.addWidget(self.overlap_label)
        stft_layout.addRow("Overlap:", overlap_layout)

        self.window_type_combo = QComboBox()
        self.window_type_combo.addItems(['hann', 'hamming', 'blackman', 'bartlett'])
        self.window_type_combo.setCurrentText('hann')
        self.window_type_combo.setToolTip("Window function type")
        stft_layout.addRow("Window Type:", self.window_type_combo)

        self.use_db_checkbox = QCheckBox("Apply dB Transform")
        self.use_db_checkbox.setChecked(True)
        self.use_db_checkbox.setToolTip("Convert magnitude to decibel scale: 20*log10(magnitude)")
        self.use_db_checkbox.stateChanged.connect(self.toggle_db_controls)
        stft_layout.addRow(self.use_db_checkbox)

        self.db_ref_spin = QDoubleSpinBox()
        self.db_ref_spin.setMinimum(1e-12)
        self.db_ref_spin.setMaximum(1e6)
        self.db_ref_spin.setValue(1e-10)
        self.db_ref_spin.setDecimals(12)
        self.db_ref_spin.setSingleStep(1e-11)
        self.db_ref_spin.setMinimumWidth(150)
        self.db_ref_spin.setToolTip("Reference value added to avoid log(0)")
        stft_layout.addRow("Reference (ε):", self.db_ref_spin)

        self.vmin_spin = QDoubleSpinBox()
        self.vmin_spin.setMinimum(-200)
        self.vmin_spin.setMaximum(0)
        self.vmin_spin.setValue(-80)
        self.vmin_spin.setSuffix(" dB")
        self.vmin_spin.setToolTip("Minimum dB value for display clipping")
        stft_layout.addRow("Min dB:", self.vmin_spin)

        self.vmax_spin = QDoubleSpinBox()
        self.vmax_spin.setMinimum(-100)
        self.vmax_spin.setMaximum(100)
        self.vmax_spin.setValue(0)
        self.vmax_spin.setSuffix(" dB")
        self.vmax_spin.setToolTip("Maximum dB value for display clipping")
        stft_layout.addRow("Max dB:", self.vmax_spin)

        stft_form = QWidget()
        stft_form.setLayout(stft_layout)
        stft_section.add_widget(stft_form)

        apply_btn = QPushButton("Apply STFT Parameters")
        apply_btn.clicked.connect(self.emit_stft_parameters)
        stft_section.add_widget(apply_btn)

        main_layout.addWidget(stft_section)
        main_layout.addStretch()

    def toggle_db_controls(self, state):
        enabled = (state == Qt.CheckState.Checked.value)
        self.db_ref_spin.setEnabled(enabled)
        self.vmin_spin.setEnabled(enabled)
        self.vmax_spin.setEnabled(enabled)

    def emit_stft_parameters(self):
        self.stft_parameters_changed.emit(
            self.window_size_spin.value(),
            self.overlap_slider.value() / 100.0,
            self.window_type_combo.currentText(),
            self.use_db_checkbox.isChecked(),
            self.db_ref_spin.value(),
            self.vmin_spin.value(),
            self.vmax_spin.value()
        )

    def get_stft_parameters(self):
        return (
            self.window_size_spin.value(),
            self.overlap_slider.value() / 100.0,
            self.window_type_combo.currentText(),
            self.use_db_checkbox.isChecked(),
            self.db_ref_spin.value(),
            self.vmin_spin.value(),
            self.vmax_spin.value()
        )

    def get_all_parameters(self):
        return {
            'window_size': self.window_size_spin.value(),
            'overlap': self.overlap_slider.value() / 100.0,
            'window_type': self.window_type_combo.currentText(),
            'use_db': self.use_db_checkbox.isChecked(),
            'db_ref': self.db_ref_spin.value(),
            'vmin': self.vmin_spin.value(),
            'vmax': self.vmax_spin.value()
        }

    def set_window_size(self, value: int):
        self.window_size_spin.setValue(value)

    def set_overlap(self, value: float):
        self.overlap_slider.setValue(int(value * 100))

    def set_window_type(self, window_type: str):
        index = self.window_type_combo.findText(window_type)
        if index >= 0:
            self.window_type_combo.setCurrentIndex(index)

    def set_db_transform(self, use_db: bool, db_ref: float = 1e-10, vmin: float = -80, vmax: float = 0):
        self.use_db_checkbox.setChecked(use_db)
        self.db_ref_spin.setValue(db_ref)
        self.vmin_spin.setValue(vmin)
        self.vmax_spin.setValue(vmax)


class FFTParameterPanel(QWidget):
    """Panel for controlling FFT parameters."""

    fft_parameters_changed = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)

        fft_section = CollapsibleSection("FFT Parameters")
        fft_layout = QFormLayout()
        fft_layout.setContentsMargins(0, 0, 0, 0)

        self.fft_nperseg_spin = QSpinBox()
        self.fft_nperseg_spin.setMinimum(64)
        self.fft_nperseg_spin.setMaximum(2_147_483_647)
        self.fft_nperseg_spin.setValue(256)
        self.fft_nperseg_spin.setSingleStep(64)
        self.fft_nperseg_spin.setToolTip("FFT segment size (number of samples per FFT window)")
        fft_layout.addRow("Segment Size:", self.fft_nperseg_spin)

        self.fft_window_combo = QComboBox()
        self.fft_window_combo.addItems(['hann', 'hamming', 'blackman', 'bartlett'])
        self.fft_window_combo.setCurrentText('hann')
        self.fft_window_combo.setToolTip("Window function type for FFT")
        fft_layout.addRow("Window:", self.fft_window_combo)

        self.fft_channel_combo = QComboBox()
        self.fft_channel_combo.addItem("Channel 1")
        self.fft_channel_combo.setToolTip("Select channel for FFT analysis")
        fft_layout.addRow("Channel:", self.fft_channel_combo)

        fft_form = QWidget()
        fft_form.setLayout(fft_layout)
        fft_section.add_widget(fft_form)

        apply_btn = QPushButton("Apply FFT Parameters")
        apply_btn.clicked.connect(self.emit_fft_parameters)
        fft_section.add_widget(apply_btn)

        main_layout.addWidget(fft_section)
        main_layout.addStretch()

    def emit_fft_parameters(self):
        self.fft_parameters_changed.emit(
            self.fft_nperseg_spin.value(),
            self.fft_window_combo.currentText()
        )

    def get_fft_parameters(self):
        return (
            self.fft_nperseg_spin.value(),
            self.fft_window_combo.currentText()
        )

    def set_fft_parameters(self, nperseg: int, window: str):
        self.fft_nperseg_spin.setValue(nperseg)
        index = self.fft_window_combo.findText(window)
        if index >= 0:
            self.fft_window_combo.setCurrentIndex(index)

    def get_selected_fft_channel(self):
        return self.fft_channel_combo.currentIndex()

    def update_channel_list(self, channel_names: list):
        self.fft_channel_combo.clear()
        self.fft_channel_combo.addItems(channel_names)
