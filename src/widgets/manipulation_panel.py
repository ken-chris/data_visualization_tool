"""
ManipulationPanel — left-sidebar panel listing enabled data manipulation tools.

Each enabled DataManipulation subclass gets a CollapsibleSection containing:
  - A channel picker (QComboBox)
  - Auto-generated controls from the class's `options` dict
  - An Apply button

Emits `manipulation_applied(object, int, dict)`:
    (manipulation_instance, channel_idx, option_values)
"""
from __future__ import annotations

from typing import Dict, List, Tuple, Type

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.manipulations.base import DataManipulation, manipulation_registry
from src.widgets.parameter_panel import CollapsibleSection


class _OptionWidget(QWidget):
    """Auto-generated controls for a single manipulation's options dict."""

    def __init__(self, options: dict, parent=None):
        super().__init__(parent)
        self._widgets: Dict[str, QWidget] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        for key, spec in options.items():
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(spec.get("label", key))
            row_layout.addWidget(label)

            opt_type = spec.get("type", "dropdown")
            if opt_type == "dropdown":
                combo = QComboBox()
                for member in spec.get("members", []):
                    combo.addItem(member)
                default = spec.get("default")
                if default:
                    idx = combo.findText(default)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                row_layout.addWidget(combo)
                self._widgets[key] = combo
            elif opt_type == "spinbox":
                spin = QDoubleSpinBox()
                spin.setMinimum(spec.get("min", 0.0))
                spin.setMaximum(spec.get("max", 1e9))
                spin.setSingleStep(spec.get("step", 1.0))
                spin.setValue(spec.get("default", 0.0))
                row_layout.addWidget(spin)
                self._widgets[key] = spin
            elif opt_type == "checkbox":
                cb = QCheckBox()
                cb.setChecked(bool(spec.get("default", False)))
                row_layout.addWidget(cb)
                self._widgets[key] = cb
            elif opt_type in ("float", "int", "text"):
                le = QLineEdit()
                if opt_type == "float":
                    le.setPlaceholderText(str(spec.get("placeholder", "0.0")))
                elif opt_type == "int":
                    le.setPlaceholderText(str(spec.get("placeholder", "0")))
                else:
                    le.setPlaceholderText(str(spec.get("placeholder", "")))
                default = spec.get("default", "")
                le.setText(str(default) if default != "" else "")
                row_layout.addWidget(le)
                self._widgets[key] = (opt_type, le)

            layout.addWidget(row)

    def get_values(self) -> dict:
        values = {}
        for key, widget in self._widgets.items():
            if isinstance(widget, QComboBox):
                values[key] = widget.currentText()
            elif isinstance(widget, QDoubleSpinBox):
                values[key] = widget.value()
            elif isinstance(widget, QCheckBox):
                values[key] = widget.isChecked()
            elif isinstance(widget, tuple):
                kind, le = widget
                text = le.text().strip()
                if kind == "int":
                    try:
                        values[key] = int(text)
                    except ValueError:
                        values[key] = None
                elif kind == "float":
                    try:
                        values[key] = float(text)
                    except ValueError:
                        values[key] = None
                else:  # "text"
                    values[key] = text
        return values


class ManipulationPanel(QWidget):
    """Left-sidebar panel listing enabled data manipulation tools."""

    manipulation_applied = pyqtSignal(object, int, str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled_names: List[str] = []
        self._channel_info: List[Tuple[str, int, str]] = []

        self._container_layout = QVBoxLayout(self)
        self._container_layout.setContentsMargins(4, 4, 4, 4)
        self._container_layout.setSpacing(4)
        self._container_layout.addStretch()

    def set_enabled(self, enabled_names: List[str]):
        """Set which manipulation names are shown. Call refresh_channels after."""
        self._enabled_names = list(enabled_names)

    def refresh_channels(self, channel_info: List[Tuple[str, int, str]]):
        """
        Rebuild the panel with current channels.
        channel_info: list of (dataset_id, channel_idx, channel_name)
        """
        self._channel_info = list(channel_info)
        self._rebuild()

    def _rebuild(self):
        """Remove all sections and rebuild from enabled list."""
        while self._container_layout.count() > 1:
            item = self._container_layout.takeAt(0)
            w = item.widget()  # save reference — item.widget() may return None after setParent
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        enabled_classes = [
            cls for cls in manipulation_registry if cls.name in self._enabled_names
        ]

        multi_dataset = len({dataset_id for dataset_id, _, _ in self._channel_info}) > 1

        for cls in enabled_classes:
            section = self._build_section(cls, multi_dataset)
            self._container_layout.insertWidget(
                self._container_layout.count() - 1, section
            )

    def _build_section(
        self, cls: Type[DataManipulation], multi_dataset: bool
    ) -> CollapsibleSection:
        section = CollapsibleSection(cls.name)

        if cls.description:
            desc = QLabel(cls.description)
            desc.setWordWrap(True)
            desc.setStyleSheet("color: #555; font-size: 10px; margin-bottom: 4px;")
            section.add_widget(desc)

        ch_label = QLabel("Channel:")
        section.add_widget(ch_label)
        ch_combo = QComboBox()
        for dataset_id, ch_idx, ch_name in self._channel_info:
            display = f"{dataset_id} / {ch_name}" if multi_dataset else f"{ch_name}"
            ch_combo.addItem(display, (dataset_id, ch_idx))
        section.add_widget(ch_combo)

        option_widget = _OptionWidget(cls.options)
        section.add_widget(option_widget)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(
            lambda checked=False, klass=cls, combo=ch_combo, opts=option_widget: self._on_apply(
                klass, combo, opts
            )
        )
        section.add_widget(apply_btn)

        return section

    def _on_apply(
        self,
        cls: Type[DataManipulation],
        ch_combo: QComboBox,
        option_widget: _OptionWidget,
    ):
        item_data = ch_combo.currentData()
        if item_data is None:
            return
        dataset_id, channel_idx = item_data
        option_values = option_widget.get_values()
        instance = cls()
        self.manipulation_applied.emit(
            instance, channel_idx, dataset_id, option_values
        )
