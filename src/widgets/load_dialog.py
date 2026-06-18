from __future__ import annotations

from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class LoadDialog(QDialog):
    def __init__(self, filename: str, existing_boxes: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle('Load Dataset')
        self.filename = filename

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(QLabel(f'Loaded file: {filename}'))

        self.new_box_radio = QRadioButton('Create new box')
        self.new_box_radio.setChecked(True)
        self.existing_box_radio = QRadioButton('Add channels to existing box')

        main_layout.addWidget(self.new_box_radio)
        self.new_options = self._create_layout_options()
        main_layout.addWidget(self.new_options['widget'])

        main_layout.addWidget(self.existing_box_radio)
        existing_widget = QWidget()
        existing_layout = QVBoxLayout(existing_widget)
        existing_layout.setContentsMargins(24, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(QLabel('Box'))
        self.existing_box_combo = QComboBox()
        self.existing_box_combo.addItems(existing_boxes)
        self.existing_box_combo.setEnabled(bool(existing_boxes))
        row.addWidget(self.existing_box_combo)
        existing_layout.addLayout(row)
        self.existing_options = self._create_layout_options()
        existing_layout.addWidget(self.existing_options['widget'])
        main_layout.addWidget(existing_widget)
        self.existing_group_widget = existing_widget

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        self.new_box_radio.toggled.connect(self._update_visibility)
        self.existing_box_radio.toggled.connect(self._update_visibility)

        if not existing_boxes:
            self.existing_box_radio.setEnabled(False)
        self._update_visibility()

    def _create_layout_options(self):
        group_box = QGroupBox('Layout')
        layout = QVBoxLayout(group_box)
        separate_radio = QRadioButton('One box per channel (separate)')
        overlay_radio = QRadioButton('All channels in one box (overlay)')
        separate_radio.setChecked(True)
        layout.addWidget(separate_radio)
        layout.addWidget(overlay_radio)

        button_group = QButtonGroup(group_box)
        button_group.addButton(separate_radio)
        button_group.addButton(overlay_radio)
        return {
            'widget': group_box,
            'separate': separate_radio,
            'overlay': overlay_radio,
            'group': button_group,
        }

    def _update_visibility(self):
        use_new = self.new_box_radio.isChecked()
        self.new_options['widget'].setVisible(use_new)
        self.existing_group_widget.setVisible(not use_new)

    def get_result(self) -> dict:
        if self.existing_box_radio.isChecked() and self.existing_box_combo.count() > 0:
            action = 'existing'
            layout = 'overlay' if self.existing_options['overlay'].isChecked() else 'separate'
            return {
                'action': action,
                'box_name': self.existing_box_combo.currentText(),
                'layout': layout,
            }
        layout = 'overlay' if self.new_options['overlay'].isChecked() else 'separate'
        return {
            'action': 'new',
            'layout': layout,
        }
