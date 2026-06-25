from __future__ import annotations

"""
Time series viewer widget using PyQtGraph.
"""
import os
import threading
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QDateTime, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QComboBox, QScrollArea
)

from src.models.sensor_data import SensorData
from src.models.annotation import Annotation
from src.widgets.plot_box import PlotBox


DEFAULT_TRACE_COLORS = [
    (31, 119, 180),
    (214, 39, 40),
    (44, 160, 44),
    (148, 103, 189),
    (255, 127, 14),
    (23, 190, 207),
    (140, 86, 75),
]


def normalize_region(start: float, end: float) -> Tuple[float, float]:
    """Ensure start <= end for region setting."""
    return (min(start, end), max(start, end))


class AnnotationRegion(pg.LinearRegionItem):
    """
    Custom LinearRegionItem with reliable click detection.
    Works around PyQtGraph's mouse capture during drag by using mouseClickEvent.
    Includes hover visual feedback and debouncing.
    """

    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptHoverEvents(True)

        self.last_click_time = 0
        self.click_debounce_ms = 200
        self.base_brush = None

    def mouseClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            current_time = QDateTime.currentMSecsSinceEpoch()
            time_since_last = current_time - self.last_click_time
            if time_since_last > self.click_debounce_ms:
                self.clicked.emit()
                self.last_click_time = current_time
                event.accept()
        else:
            super().mouseClickEvent(event)

    def hoverEnterEvent(self, event):
        if not self.base_brush:
            self.base_brush = self.brush
        current_brush = self.brush
        hover_brush = pg.mkBrush(current_brush.color())
        current_alpha = current_brush.color().alpha()
        hover_alpha = min(current_alpha + 40, 255)
        color = hover_brush.color()
        color.setAlpha(hover_alpha)
        hover_brush.setColor(color)
        self.setBrush(hover_brush)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.base_brush:
            self.setBrush(self.base_brush)
        super().hoverLeaveEvent(event)


class _ResizeHandle(QWidget):
    """
    Thin draggable bar placed below each PlotBox.
    Dragging it vertically resizes the box above.
    """

    def __init__(self, target_box: "PlotBox", parent=None):
        super().__init__(parent)
        self._target = target_box
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
            new_h = max(12, self._drag_start_height + delta)
            self._target.setFixedHeight(new_h)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_y = None
            self._drag_start_height = None
            event.accept()


class TimeSeriesWidget(QWidget):
    """
    Widget for displaying time series data with interactive region selection.
    Uses a flexible plot-box layout where each box can overlay traces from any dataset.
    """

    region_changed = pyqtSignal(float, float)
    annotations_changed = pyqtSignal()
    annotation_selected = pyqtSignal(object)
    view_range_changed = pyqtSignal(float, float)
    playback_finished = pyqtSignal()
    playback_stopped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.datasets: Dict[str, SensorData] = {}
        self.plot_boxes: List[PlotBox] = []
        self.region_items: List[pg.LinearRegionItem] = []
        self._box_counter = 0

        self.annotations: List[Annotation] = []
        self.annotation_regions: Dict[Annotation, List[AnnotationRegion]] = {}
        self.active_label: str = 'Label1'
        self.active_color: tuple = (255, 0, 0)
        self.selected_annotation: Optional[Annotation] = None

        self.is_playing: bool = False
        self.play_button: Optional[QPushButton] = None
        self.stop_button: Optional[QPushButton] = None
        self.channel_combo: Optional[QComboBox] = None
        self.stop_in_progress: bool = False
        self.force_stop_requested: bool = False

        self.playback_lock = threading.Lock()
        self.playback_thread_finished = threading.Event()
        self.playback_thread_finished.set()

        self.is_updating_range = False

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.init_ui()

        self.playback_finished.connect(self.on_playback_finished)
        self.playback_stopped.connect(self.on_playback_stopped)

    @property
    def sensor_data(self) -> Optional[SensorData]:
        return next(iter(self.datasets.values()), None)

    @property
    def plot_widgets(self) -> List[pg.PlotWidget]:
        return [box.get_plot_widget() for box in self.plot_boxes]

    @property
    def plot_items(self) -> List[pg.PlotDataItem]:
        return [item for box in self.plot_boxes for item in box._plot_items.values()]

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area containing all plot boxes (with per-box resize handles)
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._plots_container = QWidget()
        self._plots_layout = QVBoxLayout(self._plots_container)
        self._plots_layout.setContentsMargins(0, 0, 0, 0)
        self._plots_layout.setSpacing(0)
        self._plots_layout.addStretch()
        self._scroll_area.setWidget(self._plots_container)
        main_layout.addWidget(self._scroll_area, stretch=1)

        controls_layout = QHBoxLayout()

        controls_layout.addWidget(QLabel('Region:'))

        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText('Start (s)')
        self.start_edit.setMaximumWidth(100)
        self.start_edit.returnPressed.connect(self.update_region_from_inputs)
        controls_layout.addWidget(self.start_edit)

        controls_layout.addWidget(QLabel('to'))

        self.end_edit = QLineEdit()
        self.end_edit.setPlaceholderText('End (s)')
        self.end_edit.setMaximumWidth(100)
        self.end_edit.returnPressed.connect(self.update_region_from_inputs)
        controls_layout.addWidget(self.end_edit)

        apply_btn = QPushButton('Apply')
        apply_btn.clicked.connect(self.update_region_from_inputs)
        controls_layout.addWidget(apply_btn)

        jump_to_btn = QPushButton('Jump To')
        jump_to_btn.clicked.connect(self.jump_to_range)
        jump_to_btn.setToolTip('Jump to the specified time range (sets the zoom/pan)')
        controls_layout.addWidget(jump_to_btn)

        home_selection_btn = QPushButton('Home Selection')
        home_selection_btn.clicked.connect(self.home_selection)
        home_selection_btn.setToolTip('Move selection to 10%-30% of currently visible segment')
        home_selection_btn.setMaximumWidth(140)
        controls_layout.addWidget(home_selection_btn)

        select_all_btn = QPushButton('Select All')
        select_all_btn.clicked.connect(self.select_all)
        select_all_btn.setToolTip('Set region to cover all loaded data')
        controls_layout.addWidget(select_all_btn)

        controls_layout.addStretch()

        create_annotation_btn = QPushButton('Create Annotation from Region')
        create_annotation_btn.clicked.connect(self.create_annotation_from_region)
        controls_layout.addWidget(create_annotation_btn)

        delete_selected_btn = QPushButton('Delete Selected Annotation')
        delete_selected_btn.clicked.connect(self.delete_selected_annotation)
        delete_selected_btn.setToolTip('Click an annotation to select it, then click this button to delete')
        controls_layout.addWidget(delete_selected_btn)

        clear_annotations_btn = QPushButton('Clear All Annotations')
        clear_annotations_btn.clicked.connect(self.clear_all_annotations)
        controls_layout.addWidget(clear_annotations_btn)

        main_layout.addLayout(controls_layout)

    def _next_box_name(self) -> str:
        self._box_counter += 1
        return f'Box {self._box_counter}'

    def _default_trace_color(self, channel_idx: int) -> tuple[int, int, int]:
        return DEFAULT_TRACE_COLORS[channel_idx % len(DEFAULT_TRACE_COLORS)]

    def _update_channel_combo_for_sensor_data(self, sensor_data: SensorData):
        if self.channel_combo is None:
            return
        self.channel_combo.clear()
        for i, channel_name in enumerate(sensor_data.channel_names):
            self.channel_combo.addItem(f'Channel {i}: {channel_name}', i)
        if self.channel_combo.count() > 0:
            self.channel_combo.setCurrentIndex(0)

    def _configure_box(self, box: PlotBox):
        box.view_range_changed.connect(self.on_view_range_changed)
        box.region_item.sigRegionChanged.connect(
            lambda _=None, item=box.region_item: self.on_region_changed_internal(item)
        )

    def _add_plot_box(self, box: PlotBox):
        self.plot_boxes.append(box)
        self._configure_box(box)
        # Give each new box a concrete default height so the scroll area
        # knows the total content size and can scroll when boxes overflow.
        if not box.minimumHeight() or box.height() < 220:
            box.setFixedHeight(220)
        # Insert before the trailing stretch
        insert_pos = self._plots_layout.count() - 1
        self._plots_layout.insertWidget(insert_pos, box)
        self._plots_layout.insertWidget(insert_pos + 1, _ResizeHandle(box))

    def remove_box(self, box: PlotBox):
        """Remove a single PlotBox and its associated ResizeHandle from the layout."""
        if box not in self.plot_boxes:
            return
        self.plot_boxes.remove(box)
        if box.region_item in self.region_items:
            self.region_items.remove(box.region_item)

        # Remove the box and its immediately-following ResizeHandle from the layout
        idx = self._plots_layout.indexOf(box)
        if idx >= 0:
            # ResizeHandle is inserted right after the box
            handle_item = self._plots_layout.itemAt(idx + 1) if idx + 1 < self._plots_layout.count() else None
            self._plots_layout.removeWidget(box)
            box.setParent(None)
            box.deleteLater()
            if handle_item and handle_item.widget() and not isinstance(handle_item.widget(), PlotBox):
                hw = handle_item.widget()
                self._plots_layout.removeWidget(hw)
                hw.setParent(None)
                hw.deleteLater()

        self._relink_x_axes()

    def _find_plot_box(self, box_name: str) -> Optional[PlotBox]:
        for box in self.plot_boxes:
            if box.box_name == box_name:
                return box
        return None

    def _relink_x_axes(self):
        if not self.plot_boxes:
            return
        first_plot = self.plot_boxes[0].get_plot_widget()
        for box in self.plot_boxes[1:]:
            box.get_plot_widget().setXLink(first_plot)

    def _refresh_region_items(self):
        self.region_items = [box.region_item for box in self.plot_boxes]

    def _add_existing_annotations_to_boxes(self, boxes: List[PlotBox]):
        if not boxes:
            return
        for annotation in self.annotations:
            self._add_annotation_to_boxes(annotation, boxes)
        if self.selected_annotation is not None:
            self._update_annotation_appearance(self.selected_annotation, selected=True)

    def refresh_all_traces(self):
        for box in self.plot_boxes:
            box.refresh_traces(self.datasets)

    def set_data(self, sensor_data: SensorData):
        dataset_id = os.path.basename(sensor_data.filename) if sensor_data.filename else f'dataset_{len(self.datasets) + 1}'
        self.clear_plots()
        self.datasets[dataset_id] = sensor_data
        self.add_dataset(dataset_id, sensor_data, 'separate', None)
        self._update_channel_combo_for_sensor_data(sensor_data)

    def add_dataset(self, dataset_id: str, sensor_data: SensorData, layout: str, target_box_name: str | None):
        self.datasets[dataset_id] = sensor_data
        current_region = self.get_selected_region()
        new_boxes: List[PlotBox] = []

        if target_box_name:
            target_box = self._find_plot_box(target_box_name)
            if target_box is None:
                target_box = PlotBox(self._next_box_name(), self.datasets, self)
                self._add_plot_box(target_box)
                new_boxes.append(target_box)
            for channel_idx in range(sensor_data.n_channels):
                target_box.add_trace(dataset_id, channel_idx, self._default_trace_color(channel_idx), 1.0)
        elif layout == 'overlay':
            box = PlotBox(self._next_box_name(), self.datasets, self)
            for channel_idx in range(sensor_data.n_channels):
                box.add_trace(dataset_id, channel_idx, self._default_trace_color(channel_idx), 1.0)
            self._add_plot_box(box)
            new_boxes.append(box)
        else:
            for channel_idx in range(sensor_data.n_channels):
                box = PlotBox(self._next_box_name(), self.datasets, self)
                box.add_trace(dataset_id, channel_idx, self._default_trace_color(channel_idx), 1.0)
                self._add_plot_box(box)
                new_boxes.append(box)

        self._relink_x_axes()
        self._refresh_region_items()

        if current_region is not None:
            start, end = current_region
            for box in new_boxes:
                box.set_region(start, end)
            self.update_inputs_from_region()
        else:
            self.initialize_region()

        self._add_existing_annotations_to_boxes(new_boxes)

        for box in new_boxes:
            box.get_plot_widget().autoRange()

        self._update_channel_combo_for_sensor_data(sensor_data)
        self.on_view_range_changed()

    def get_plot_boxes(self) -> List[str]:
        return [box.box_name for box in self.plot_boxes]

    def clear_plots(self):
        # Remove all widgets except the trailing stretch
        while self._plots_layout.count() > 1:
            item = self._plots_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
        self.plot_boxes.clear()
        self.region_items.clear()
        self.annotation_regions.clear()

    def initialize_region(self):
        sensor_data = self.sensor_data
        if sensor_data is None or not self.region_items:
            return
        duration = sensor_data.duration
        start = sensor_data.timestamps[0] + duration * 0.1
        end = sensor_data.timestamps[0] + duration * 0.2
        for region_item in self.region_items:
            region_item.blockSignals(True)
            region_item.setRegion(list(normalize_region(start, end)))
            region_item.blockSignals(False)
        self.update_inputs_from_region()
        self.region_changed.emit(start, end)

    def on_region_changed_internal(self, changed_item: pg.LinearRegionItem):
        if not self.region_items:
            return
        start, end = changed_item.getRegion()
        start, end = normalize_region(start, end)
        for region_item in self.region_items:
            if region_item != changed_item:
                region_item.blockSignals(True)
                region_item.setRegion([start, end])
                region_item.blockSignals(False)
        self.start_edit.setText(f'{start:.3f}')
        self.end_edit.setText(f'{end:.3f}')
        self.region_changed.emit(start, end)

    def on_view_range_changed(self, *args):
        if self.is_updating_range or not self.plot_boxes:
            return
        view_box = self.plot_boxes[0].get_plot_widget().getViewBox()
        x_range = view_box.viewRange()[0]
        self.view_range_changed.emit(x_range[0], x_range[1])

    def update_inputs_from_region(self):
        if not self.region_items:
            return
        start, end = self.region_items[0].getRegion()
        self.start_edit.setText(f'{start:.3f}')
        self.end_edit.setText(f'{end:.3f}')

    def update_region_from_inputs(self):
        if not self.region_items:
            return
        try:
            start = float(self.start_edit.text())
            end = float(self.end_edit.text())
            start, end = normalize_region(start, end)
            for region_item in self.region_items:
                region_item.setRegion([start, end])
        except ValueError:
            self.update_inputs_from_region()

    def home_selection(self):
        if not self.plot_boxes or not self.region_items:
            return
        view_box = self.plot_boxes[0].get_plot_widget().getViewBox()
        x_min, x_max = view_box.viewRange()[0]
        segment_size = x_max - x_min
        start = x_min + segment_size * 0.1
        end = x_min + segment_size * 0.3
        for region_item in self.region_items:
            region_item.setRegion(list(normalize_region(start, end)))
        self.update_inputs_from_region()

    def select_all(self):
        """Set the selection region to the full data range."""
        sensor_data = self.sensor_data
        if sensor_data is None or not self.region_items:
            return
        start = float(sensor_data.timestamps[0])
        end = float(sensor_data.timestamps[-1])
        for region_item in self.region_items:
            region_item.setRegion([start, end])
        self.update_inputs_from_region()
        self.region_changed.emit(start, end)

    def jump_to_range(self):
        try:
            start = float(self.start_edit.text())
            end = float(self.end_edit.text())
            start, end = normalize_region(start, end)
            self.set_x_range(start, end)
            main_window = self.window()
            if main_window and hasattr(main_window, 'spectrogram_widget'):
                main_window.spectrogram_widget.set_x_range(start, end)
        except ValueError:
            try:
                main_window = self.window()
                if main_window and hasattr(main_window, 'statusBar'):
                    main_window.statusBar().showMessage('? Invalid time values for jump', 2000)
            except Exception:
                pass

    def get_selected_region(self):
        if not self.region_items:
            return None
        return self.region_items[0].getRegion()

    def get_selected_data(self):
        sensor_data = self.sensor_data
        if sensor_data is None or not self.region_items:
            return None, None
        start, end = self.region_items[0].getRegion()
        return sensor_data.get_time_slice(start, end)

    def set_x_range(self, x_min: float, x_max: float):
        self.is_updating_range = True
        try:
            for box in self.plot_boxes:
                box.get_plot_widget().setXRange(x_min, x_max, padding=0)
        finally:
            self.is_updating_range = False

    def set_active_label(self, label: str, color: tuple):
        self.active_label = label
        self.active_color = color

    def create_annotation_from_region(self):
        sensor_data = self.sensor_data
        if not self.region_items or sensor_data is None:
            QMessageBox.warning(self, 'No Data', 'Please load data first.')
            return
        start, end = self.region_items[0].getRegion()
        for existing_annotation in self.annotations:
            if not (end < existing_annotation.start_time or start > existing_annotation.end_time):
                reply = QMessageBox.question(
                    self,
                    'Overlapping Annotation',
                    f"This region overlaps with existing annotation '{existing_annotation.label}' "
                    f"({existing_annotation.start_time:.2f}s - {existing_annotation.end_time:.2f}s).\n\n"
                    'Create annotation anyway?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
                break
        annotation = Annotation(
            label=self.active_label,
            start_time=start,
            end_time=end,
            color=self.active_color,
            notes='',
            sample_rate=sensor_data.sample_rate if sensor_data else None
        )
        self.annotations.append(annotation)
        self.add_annotation_to_plots(annotation)
        self.annotations_changed.emit()

    def _add_annotation_to_boxes(self, annotation: Annotation, boxes: List[PlotBox]):
        if not boxes:
            return
        region_items = self.annotation_regions.setdefault(annotation, [])
        for box in boxes:
            plot_widget = box.get_plot_widget()
            r, g, b = annotation.color
            region = AnnotationRegion(
                values=[annotation.start_time, annotation.end_time],
                brush=pg.mkBrush(r, g, b, 60),
                pen=pg.mkPen(color=(r, g, b), width=2),
                movable=True
            )
            region.sigRegionChanged.connect(
                lambda rgn=region, ann=annotation: self.on_annotation_region_changed(ann, rgn)
            )
            region.clicked.connect(
                lambda ann=annotation: self.select_annotation(ann)
            )
            region._plot_widget = plot_widget
            plot_widget.addItem(region)
            region_items.append(region)

    def add_annotation_to_plots(self, annotation: Annotation):
        self._add_annotation_to_boxes(annotation, self.plot_boxes)

    def on_annotation_region_changed(self, annotation: Annotation, region: pg.LinearRegionItem):
        start, end = region.getRegion()
        start, end = normalize_region(start, end)
        annotation.start_time = start
        annotation.end_time = end
        if annotation in self.annotation_regions:
            for other_region in self.annotation_regions[annotation]:
                if other_region != region:
                    other_region.blockSignals(True)
                    other_region.setRegion([start, end])
                    other_region.blockSignals(False)
        self.annotations_changed.emit()

    def select_annotation(self, annotation: Annotation):
        if self.selected_annotation == annotation:
            self._update_annotation_appearance(annotation, selected=False)
            self.selected_annotation = None
            self.annotation_selected.emit(None)
        else:
            if self.selected_annotation and self.selected_annotation in self.annotation_regions:
                self._update_annotation_appearance(self.selected_annotation, selected=False)
            self.selected_annotation = annotation
            self._update_annotation_appearance(annotation, selected=True)
            self.annotation_selected.emit(annotation)

    def _update_annotation_appearance(self, annotation: Annotation, selected: bool):
        if annotation not in self.annotation_regions:
            return
        r, g, b = annotation.color
        if selected:
            pen = pg.mkPen(color=(r, g, b), width=5)
            brush = pg.mkBrush(r, g, b, 180)
        else:
            pen = pg.mkPen(color=(r, g, b), width=2)
            brush = pg.mkBrush(r, g, b, 60)
        for region in self.annotation_regions[annotation]:
            for line in region.lines:
                line.setPen(pen)
            region.setBrush(brush)
            region.base_brush = brush

    def delete_selected_annotation(self):
        if not self.selected_annotation:
            QMessageBox.information(
                self,
                'No Selection',
                'Please click an annotation to select it first.'
            )
            return
        annotation = self.selected_annotation
        self.selected_annotation = None
        self.delete_annotation(annotation)

    def delete_annotation(self, annotation: Annotation):
        if annotation in self.annotation_regions:
            for region in self.annotation_regions[annotation]:
                plot_widget = getattr(region, '_plot_widget', None)
                if plot_widget is not None:
                    plot_widget.removeItem(region)
            del self.annotation_regions[annotation]
        if annotation in self.annotations:
            self.annotations.remove(annotation)
        if self.selected_annotation == annotation:
            self.selected_annotation = None
            self.annotation_selected.emit(None)
        self.annotations_changed.emit()
        status_bar = self.statusBar()
        if status_bar:
            status_bar.showMessage(f"Deleted annotation '{annotation.label}'", 3000)

    def clear_all_annotations(self):
        if not self.annotations:
            QMessageBox.information(self, 'No Annotations', 'No annotations to clear.')
            return
        reply = QMessageBox.question(
            self,
            'Clear All Annotations',
            f'Delete all {len(self.annotations)} annotations?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._clear_all_annotations_internal()

    def _clear_all_annotations_internal(self):
        for annotation, regions in list(self.annotation_regions.items()):
            for region in regions:
                plot_widget = getattr(region, '_plot_widget', None)
                if plot_widget is not None:
                    plot_widget.removeItem(region)
        self.annotations.clear()
        self.annotation_regions.clear()
        self.selected_annotation = None
        self.annotation_selected.emit(None)
        self.annotations_changed.emit()
        status_bar = self.statusBar()
        if status_bar:
            status_bar.showMessage('All annotations cleared', 3000)

    def get_annotations(self):
        return self.annotations.copy()

    def refresh_annotation_regions(self):
        for annotation in self.annotations:
            if annotation in self.annotation_regions:
                start, end = normalize_region(annotation.start_time, annotation.end_time)
                for region in self.annotation_regions[annotation]:
                    try:
                        region.blockSignals(True)
                        region.setRegion([start, end])
                        region.blockSignals(False)
                    except RuntimeError:
                        pass

    def load_annotations(self, annotations: List[Annotation]):
        for regions in self.annotation_regions.values():
            for region in regions:
                plot_widget = getattr(region, '_plot_widget', None)
                if plot_widget is not None:
                    plot_widget.removeItem(region)
        self.annotations = []
        self.annotation_regions = {}
        self.selected_annotation = None
        self.annotation_selected.emit(None)
        for annotation in annotations:
            self.annotations.append(annotation)
            self.add_annotation_to_plots(annotation)
        self.annotations_changed.emit()

    def autoscale_y_axis(self):
        for box in self.plot_boxes:
            plot_widget = box.get_plot_widget()
            view_box = plot_widget.getViewBox()
            x_min, x_max = view_box.viewRange()[0]

            y_min_global = np.inf
            y_max_global = -np.inf

            for (dataset_id, channel_idx) in box._plot_items:
                sensor_data = box.datasets.get(dataset_id)
                if sensor_data is None:
                    continue
                timestamps = sensor_data.timestamps
                # O(log n) slice instead of full boolean mask
                i_lo = np.searchsorted(timestamps, x_min, side='left')
                i_hi = np.searchsorted(timestamps, x_max, side='right')
                if i_lo >= i_hi:
                    continue
                y_slice = sensor_data.get_channel(channel_idx)[i_lo:i_hi]
                if len(y_slice) == 0:
                    continue
                y_min_global = min(y_min_global, float(np.min(y_slice)))
                y_max_global = max(y_max_global, float(np.max(y_slice)))

            if np.isfinite(y_min_global) and np.isfinite(y_max_global):
                y_range = y_max_global - y_min_global
                if y_range > 0:
                    padding = y_range * 0.05
                    view_box.setYRange(y_min_global - padding, y_max_global + padding, padding=0)
                else:
                    view_box.setYRange(y_min_global - 1, y_max_global + 1, padding=0)
            else:
                view_box.autoRange(padding=0.02)
            view_box.setXRange(x_min, x_max, padding=0)

    def play_selected_segment(self):
        sensor_data = self.sensor_data
        if sensor_data is None or not self.region_items:
            QMessageBox.warning(self, 'No Data', 'Please load data first.')
            return
        try:
            main_window = self.window()
            if not hasattr(main_window, 'playback_lock'):
                QMessageBox.warning(self, 'Error', 'Main window not properly initialized')
                return
            main_window.start_playback(self)
            if not main_window.playback_thread_finished.wait(timeout=1.0):
                QMessageBox.warning(self, 'Playback Busy', 'Previous playback still finishing. Try again.')
                return
            with main_window.playback_lock:
                if main_window.is_playing:
                    return
                start, end = self.region_items[0].getRegion()
                timestamps, data = sensor_data.get_time_slice(start, end)
                if len(data) == 0:
                    QMessageBox.warning(self, 'Empty Region', 'Please select a valid region to play.')
                    return
                channel_idx = self.channel_combo.currentData() if self.channel_combo else 0
                audio_data = data[:, channel_idx]
                max_val = np.max(np.abs(audio_data))
                if max_val > 0:
                    audio_data = audio_data / max_val
                main_window.is_playing = True
                main_window.playback_thread_finished.clear()
                self.is_playing = True
                try:
                    if self.play_button:
                        self.play_button.setEnabled(False)
                    if self.stop_button:
                        self.stop_button.setEnabled(True)
                        self.stop_button.setStyleSheet('background-color: #ffcccc;')
                except RuntimeError as e:
                    print(f'Error updating buttons: {e}')
                try:
                    status_bar = self.statusBar()
                    if status_bar:
                        duration = len(audio_data) / sensor_data.sample_rate
                        status_bar.showMessage(f'Playing segment ({duration:.2f}s)...')
                except RuntimeError as e:
                    print(f'Error updating status bar: {e}')
                print(f'[DEBUG] Starting playback thread in timeseries (is_playing={main_window.is_playing})')
                playback_thread = threading.Thread(
                    target=self._play_audio_in_thread,
                    args=(audio_data, sensor_data.sample_rate),
                    daemon=True
                )
                playback_thread.start()
        except ImportError:
            QMessageBox.critical(
                self,
                'sounddevice Not Installed',
                'Please install sounddevice:\npip install sounddevice'
            )
        except Exception as e:
            print(f'[ERROR] Play segment error: {e}')
            self.is_playing = False
            main_window = self.window()
            if hasattr(main_window, 'playback_thread_finished'):
                main_window.is_playing = False
                main_window.playback_thread_finished.set()
            try:
                if self.play_button:
                    self.play_button.setEnabled(True)
                if self.stop_button:
                    self.stop_button.setEnabled(False)
                    self.stop_button.setStyleSheet('')
            except RuntimeError:
                pass
            QMessageBox.critical(
                self,
                'Playback Error',
                f'Error playing audio:\n{str(e)}'
            )

    def _play_audio_in_thread(self, audio_data: np.ndarray, sample_rate: int):
        main_window = self.window()
        try:
            import sounddevice as sd
            print(f'[DEBUG] Audio thread started: data shape={audio_data.shape}, sample_rate={sample_rate}')
            sd.play(audio_data, samplerate=int(sample_rate))
            sd.wait()
            print('[DEBUG] Audio thread finished (sd.wait completed)')
        except Exception as e:
            print(f'[ERROR] Playback error during sd.wait/sd.play: {e}')
        finally:
            if hasattr(main_window, 'playback_thread_finished'):
                main_window.playback_thread_finished.set()
            if not self.force_stop_requested:
                try:
                    print('[DEBUG] Emitting playback_finished signal')
                    self.playback_finished.emit()
                except Exception as e:
                    print(f'[ERROR] Error emitting playback_finished signal: {e}')
            else:
                print('[DEBUG] Force stop was requested, skipping signal emission to avoid crash')
                self.force_stop_requested = False

    def stop_playback(self):
        main_window = self.window()
        if self.stop_in_progress:
            return
        if hasattr(main_window, 'is_playing') and not main_window.is_playing:
            return
        self.stop_in_progress = True
        self.force_stop_requested = True
        print('[DEBUG] Stop playback called in timeseries')
        try:
            import sounddevice as sd
            sd.stop()
            print('[DEBUG] sd.stop() called')
        except Exception as e:
            print(f'[ERROR] Error stopping playback: {e}')
        finally:
            self.stop_in_progress = False
            if hasattr(main_window, 'playback_thread_finished'):
                print('[DEBUG] Waiting for audio thread to complete...')
                main_window.playback_thread_finished.wait(timeout=1.0)
                print('[DEBUG] Audio thread completed, now emitting playback_stopped signal')
            try:
                self.playback_stopped.emit()
            except Exception as e:
                print(f'[ERROR] Error emitting playback_stopped: {e}')

    def on_playback_finished(self):
        try:
            print('[DEBUG] Playback finished signal received')
            self.is_playing = False
            try:
                main_window = self.window()
                if main_window and hasattr(main_window, 'is_playing'):
                    main_window.is_playing = False
            except Exception as e:
                print(f'[WARNING] Could not access main_window in on_playback_finished: {e}')
            try:
                if self.play_button and self.play_button.isEnabled() == False:
                    self.play_button.setEnabled(True)
                    print('[DEBUG] Play button re-enabled')
            except Exception as e:
                print(f'[WARNING] Could not update play button: {e}')
            try:
                if self.stop_button and self.stop_button.isEnabled() == True:
                    self.stop_button.setEnabled(False)
                    self.stop_button.setStyleSheet('')
                    print('[DEBUG] Stop button disabled')
            except Exception as e:
                print(f'[WARNING] Could not update stop button: {e}')
        except Exception as e:
            print(f'[ERROR] Unhandled error in on_playback_finished: {e}')
            import traceback
            traceback.print_exc()

    def on_playback_stopped(self):
        try:
            print('[DEBUG] on_playback_stopped handler called')
            self.is_playing = False
            try:
                main_window = self.window()
                if main_window and hasattr(main_window, 'is_playing'):
                    main_window.is_playing = False
                    print('[DEBUG] Set main_window.is_playing = False')
            except Exception as e:
                print(f'[WARNING] Could not access main_window in on_playback_stopped: {e}')
            try:
                if self.play_button and self.play_button.isVisible():
                    if not self.play_button.isEnabled():
                        self.play_button.setEnabled(True)
                        print('[DEBUG] Play button re-enabled after stop')
                    else:
                        print('[DEBUG] Play button already enabled')
                else:
                    print("[DEBUG] Play button not visible or doesn't exist")
            except RuntimeError as e:
                print(f'[WARNING] RuntimeError accessing play button: {e}')
            except Exception as e:
                print(f'[WARNING] Could not update play button: {e}')
            try:
                if self.stop_button and self.stop_button.isVisible():
                    if self.stop_button.isEnabled():
                        self.stop_button.setEnabled(False)
                        self.stop_button.setStyleSheet('')
                        print('[DEBUG] Stop button disabled after stop')
                    else:
                        print('[DEBUG] Stop button already disabled')
                else:
                    print("[DEBUG] Stop button not visible or doesn't exist")
            except RuntimeError as e:
                print(f'[WARNING] RuntimeError accessing stop button: {e}')
            except Exception as e:
                print(f'[WARNING] Could not update stop button: {e}')
        except Exception as e:
            print(f'[ERROR] Unhandled error in on_playback_stopped: {e}')
            import traceback
            traceback.print_exc()

    def keyPressEvent(self, event):
        super().keyPressEvent(event)

    def statusBar(self):
        window = self.window()
        if hasattr(window, 'statusBar'):
            return window.statusBar()
        return None
