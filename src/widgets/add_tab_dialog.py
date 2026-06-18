"""Dialog shown when the '+' tab is clicked, listing available widget types."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


_WIDGET_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_tab_widget(name: str, description: str, factory: Callable):
    """Register a widget type available from the + tab dialog."""
    _WIDGET_REGISTRY[name] = {'description': description, 'factory': factory}


def get_registry() -> Dict[str, Dict[str, Any]]:
    """Return registered widget types."""
    return dict(_WIDGET_REGISTRY)


class AddTabDialog(QDialog):
    """Dialog for selecting a widget type to add as a new tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Tab")
        self.resize(380, 260)
        self.selected_name: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select a widget type to add as a new tab:"))

        self._list = QListWidget()
        for name, info in _WIDGET_REGISTRY.items():
            item = QListWidgetItem(name)
            item.setToolTip(info['description'])
            self._list.addItem(item)
        self._list.itemDoubleClicked.connect(self._accept)
        layout.addWidget(self._list)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _accept(self):
        item = self._list.currentItem()
        if item:
            self.selected_name = item.text()
            self.accept()
