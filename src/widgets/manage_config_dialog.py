"""
ManageConfigDialog — lets user choose which manipulation tools appear in the sidebar.
"""
from __future__ import annotations

import json
import os
from typing import List, Set

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.manipulations.base import manipulation_registry

_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "manipulation_config.json",
)


def load_enabled_manipulations() -> List[str]:
    """Load enabled manipulation names from config file. Returns all if file missing."""
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data.get("enabled", [cls.name for cls in manipulation_registry])
        except Exception:
            pass
    return [cls.name for cls in manipulation_registry]


def save_enabled_manipulations(enabled: List[str]):
    """Save enabled manipulation names to config file."""
    with open(_CONFIG_FILE, "w") as f:
        json.dump({"enabled": enabled}, f, indent=2)


class ManageConfigDialog(QDialog):
    """
    Dialog listing all registered manipulations with a 'Display' checkbox per row.
    """

    def __init__(self, currently_enabled: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Manipulation Tools")
        self.resize(380, 400)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Check which manipulation tools to show in the sidebar:")
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        cb_layout = QVBoxLayout(container)
        cb_layout.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(container)
        layout.addWidget(scroll)

        self._checkboxes: List[tuple[QCheckBox, str]] = []
        enabled_set: Set[str] = set(currently_enabled)

        for cls in manipulation_registry:
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 4, 0, 4)

            cb = QCheckBox(cls.name)
            cb.setChecked(cls.name in enabled_set)
            row_layout.addWidget(cb)

            if cls.description:
                desc = QLabel(f"  {cls.description}")
                desc.setStyleSheet("color: #666; font-size: 10px;")
                row_layout.addWidget(desc)

            cb_layout.addWidget(row)
            self._checkboxes.append((cb, cls.name))

        cb_layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_enabled(self) -> List[str]:
        return [name for cb, name in self._checkboxes if cb.isChecked()]
