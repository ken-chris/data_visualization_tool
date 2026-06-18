"""
Main application window.
"""
import os
import traceback
from typing import Dict, Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTabWidget, QFileDialog, QMessageBox, QStackedWidget, QDialog, QScrollArea,
    QProgressDialog,
)
from PyQt6.QtCore import Qt, QEvent, QThread, pyqtSignal as _pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence

import src.manipulations
from src.models.sensor_data import SensorData
from src.models.annotation import Annotation
from src.utils.data_loader import load_data, load_annotations_json
from src.utils.export import export_to_json, export_to_csv, save_session, load_session
from src.utils.config import AppConfig
from src.widgets.timeseries_widget import TimeSeriesWidget
from src.widgets.fft_widget import FFTWidget
from src.widgets.spectrogram_widget import SpectrogramWidget
from src.widgets.parameter_panel import STFTParameterPanel, FFTParameterPanel
from src.widgets.annotation_panel import AnnotationPanel
from src.widgets.load_dialog import LoadDialog
from src.widgets.data_mgmt_panel import DataMgmtPanel
from src.widgets.manipulation_panel import ManipulationPanel
from src.widgets.add_tab_dialog import AddTabDialog, get_registry
import src.widgets.spatial_widget  # trigger registration
from src.widgets.manage_config_dialog import (
    ManageConfigDialog,
    load_enabled_manipulations,
    save_enabled_manipulations,
)


class MainWindow(QMainWindow):
    """Main application window for sensor data annotation."""

    def __init__(self):
        super().__init__()
        self.sensor_data: Optional[SensorData] = None
        self.datasets: Dict[str, SensorData] = {}
        self.annotations: list[Annotation] = []
        self.current_annotation_label = 'Label1'
        self.config: AppConfig = AppConfig.get_default()

        self.is_syncing_views = False

        import threading
        self.playback_lock = threading.Lock()
        self.playback_thread_finished = threading.Event()
        self.playback_thread_finished.set()
        self.is_playing = False
        self.stop_in_progress = False
        self.active_playback_widget = None

        self.init_ui()
        self.installEventFilter(self)

    def init_ui(self):
        self.setWindowTitle('Sensor Data Annotation Tool')
        self.setGeometry(100, 100, 1400, 800)

        self.create_menus()
        self.statusBar().showMessage('Ready')

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.annotation_panel = AnnotationPanel()
        self.annotation_panel.label_selected.connect(self.on_label_selected)

        self.stft_panel = STFTParameterPanel()
        self.stft_panel.stft_parameters_changed.connect(self.on_stft_parameters_changed)

        self.fft_panel = FFTParameterPanel()
        self.fft_panel.fft_parameters_changed.connect(self.on_fft_parameters_changed)

        self.manipulation_panel = ManipulationPanel()
        self.manipulation_panel.manipulation_applied.connect(self.on_manipulation_applied)
        self._enabled_manipulations = load_enabled_manipulations()
        self.manipulation_panel.set_enabled(self._enabled_manipulations)

        ts_sidebar_content = QWidget()
        ts_sidebar_content_layout = QVBoxLayout(ts_sidebar_content)
        ts_sidebar_content_layout.setContentsMargins(0, 0, 0, 0)
        ts_sidebar_content_layout.setSpacing(0)
        ts_sidebar_content_layout.addWidget(self.annotation_panel)
        ts_sidebar_content_layout.addWidget(self.manipulation_panel, stretch=1)

        ts_sidebar_scroll = QScrollArea()
        ts_sidebar_scroll.setWidgetResizable(True)
        ts_sidebar_scroll.setWidget(ts_sidebar_content)

        self.left_stack = QStackedWidget()
        self.left_stack.addWidget(ts_sidebar_scroll)  # index 0 → Time Series
        self.left_stack.addWidget(self.stft_panel)         # index 1 → Spectrogram
        self.left_stack.addWidget(self.fft_panel)          # index 2 → FFT
        self.left_stack.addWidget(QWidget())               # index 3 → Data Mgmt (no sidebar)
        left_layout.addWidget(self.left_stack)

        self.tab_widget = QTabWidget()

        self.timeseries_widget = TimeSeriesWidget()
        self.timeseries_widget.datasets = self.datasets
        self.timeseries_widget.region_changed.connect(self.on_region_changed)
        self.timeseries_widget.annotations_changed.connect(self.on_annotations_changed)
        self.timeseries_widget.annotation_selected.connect(self.on_annotation_selected)
        self.timeseries_widget.view_range_changed.connect(self.on_view_range_changed)

        label, color = self.annotation_panel.get_active_label()
        if label:
            self.timeseries_widget.set_active_label(label, color)

        self.spectrogram_widget = SpectrogramWidget()
        self.spectrogram_widget.view_range_changed.connect(self.on_spectrogram_view_range_changed)
        self.spectrogram_widget.annotations_changed.connect(self.on_spectrogram_annotations_changed)
        self.spectrogram_widget.region_changed.connect(self.on_spectrogram_region_changed)
        self.fft_widget = FFTWidget()

        self.tab_widget.addTab(self.timeseries_widget, 'Time Series')
        self.tab_widget.addTab(self.spectrogram_widget, 'Spectrogram')
        self.tab_widget.addTab(self.fft_widget, 'FFT')

        self.data_mgmt_panel = DataMgmtPanel()
        self.data_mgmt_panel.load_data_requested.connect(self.open_file)
        self.data_mgmt_panel.channels_applied.connect(self.on_channels_applied)
        self.data_mgmt_panel.channel_deleted.connect(self.on_channel_deleted)
        self.data_mgmt_panel.channel_duplicated.connect(self.on_channel_duplicated)
        self.data_mgmt_panel.box_deleted.connect(self.on_box_deleted)
        self.data_mgmt_panel.box_duplicated.connect(self.on_box_duplicated)
        self.tab_widget.addTab(self.data_mgmt_panel, 'Data Mgmt')

        # "+" tab — always last; clicking it opens the add-tab dialog
        self.tab_widget.addTab(QWidget(), "+")
        self._plus_tab_index = self.tab_widget.count() - 1
        self._dynamic_tabs: list[dict] = []

        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.setCurrentIndex(3)  # Open on Data Mgmt tab by default

        splitter.addWidget(left_panel)
        splitter.addWidget(self.tab_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        main_layout.addWidget(splitter)

    def _on_tab_changed(self, index: int):
        """Switch left sidebar page; intercept '+' tab to open add-widget dialog."""
        if index == self._plus_tab_index:
            prev = max(0, index - 1)
            self.tab_widget.blockSignals(True)
            self.tab_widget.setCurrentIndex(prev)
            self.tab_widget.blockSignals(False)
            self._open_add_tab_dialog()
            return

        is_dynamic = False
        for entry in self._dynamic_tabs:
            if entry['index'] == index:
                is_dynamic = True
                sidebar = entry.get('sidebar_widget')
                if sidebar is not None:
                    if self.left_stack.indexOf(sidebar) < 0:
                        self.left_stack.addWidget(sidebar)
                    self.left_stack.setCurrentWidget(sidebar)
                else:
                    self.left_stack.setCurrentIndex(3)
                widget = entry['widget']
                if hasattr(widget, 'set_datasets'):
                    widget.set_datasets(self.datasets)
                break

        if not is_dynamic:
            if index == 3:
                self.left_stack.setCurrentIndex(3)
                self.data_mgmt_panel.refresh(
                    self.timeseries_widget.plot_boxes,
                    self.timeseries_widget.datasets,
                )
                self._refresh_manipulation_channels()
            elif index < 4:
                self.left_stack.setCurrentIndex(index)

    def _open_add_tab_dialog(self):
        dlg = AddTabDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.selected_name is None:
            return
        registry = get_registry()
        entry = registry.get(dlg.selected_name)
        if entry is None:
            return
        result = entry['factory']()
        if isinstance(result, tuple) and len(result) == 3:
            widget, sidebar, label = result
        else:
            widget, sidebar, label = result, None, dlg.selected_name

        insert_idx = self._plus_tab_index
        self.tab_widget.insertTab(insert_idx, widget, label)
        self._plus_tab_index += 1

        self._dynamic_tabs.append({
            'index': insert_idx,
            'widget': widget,
            'sidebar_widget': sidebar,
            'label': label,
        })

        if sidebar is not None:
            self.left_stack.addWidget(sidebar)

        # Wire up manipulation panel if the widget exposes one
        if hasattr(widget, 'manip_panel'):
            widget.manip_panel.manipulation_applied.connect(
                lambda inst, ch_idx, ds_id, opts, w=widget:
                    self.on_spatial_manipulation_applied(inst, ch_idx, ds_id, opts, w)
            )
            widget.refresh_manip_channels(self.datasets)

        self.tab_widget.setCurrentIndex(insert_idx)

        if hasattr(widget, 'set_datasets'):
            widget.set_datasets(self.datasets)

    def on_channels_applied(self, configs: list):
        """
        Handle channel name edits and FFT/STFT filter changes from Data Mgmt panel.
        configs: list of {dataset_id, channel_idx, name, fft, stft}
        """
        # Update channel names in all datasets
        for cfg in configs:
            sensor_data = self.datasets.get(cfg['dataset_id'])
            if sensor_data and cfg['channel_idx'] < len(sensor_data.channel_names):
                sensor_data.channel_names[cfg['channel_idx']] = cfg['name']

        # Apply channel filters to FFT and Spectrogram for the most recent dataset
        if self.sensor_data is not None:
            dataset_id = os.path.basename(self.sensor_data.filename) if self.sensor_data.filename else None
            if dataset_id:
                fft_channels = [
                    cfg['channel_idx'] for cfg in configs
                    if cfg['dataset_id'] == dataset_id and cfg['fft']
                ]
                stft_channels = [
                    cfg['channel_idx'] for cfg in configs
                    if cfg['dataset_id'] == dataset_id and cfg['stft']
                ]
                self.fft_widget.set_active_channels(fft_channels)
                self.spectrogram_widget.set_active_channels(stft_channels)
                # Refresh FFT panel channel list to match new names
                self.fft_panel.update_channel_list(self.sensor_data.channel_names)

        # Refresh timeseries legends (names may have changed)
        for box in self.timeseries_widget.plot_boxes:
            box.refresh_traces(self.timeseries_widget.datasets)

        # Refresh Data Mgmt panel so names update in box sections too
        self.data_mgmt_panel.refresh(
            self.timeseries_widget.plot_boxes,
            self.timeseries_widget.datasets,
        )

    def on_channel_deleted(self, dataset_id: str, channel_idx: int):
        """Remove a channel from its dataset and refresh all views."""
        sensor_data = self.datasets.get(dataset_id)
        if sensor_data is None or sensor_data.n_channels <= 1:
            QMessageBox.warning(
                self,
                "Cannot Delete",
                "Cannot delete the only channel in a dataset.",
            )
            return

        import numpy as np

        sensor_data.data = np.delete(sensor_data.data, channel_idx, axis=1)
        sensor_data.channel_names.pop(channel_idx)

        for box in self.timeseries_widget.plot_boxes:
            to_remove = []
            for trace in list(box.traces):
                if trace['dataset_id'] == dataset_id:
                    if trace['channel_idx'] == channel_idx:
                        to_remove.append((trace['dataset_id'], trace['channel_idx']))
                    elif trace['channel_idx'] > channel_idx:
                        trace['channel_idx'] -= 1
            for did, cidx in to_remove:
                box.remove_trace(did, cidx)
            box.refresh_traces(self.timeseries_widget.datasets)

        if self.sensor_data is sensor_data:
            self.fft_widget.set_data(sensor_data)
            self.spectrogram_widget.set_data(sensor_data)
            self.fft_panel.update_channel_list(sensor_data.channel_names)

        self.data_mgmt_panel.refresh(
            self.timeseries_widget.plot_boxes,
            self.timeseries_widget.datasets,
        )
        self._refresh_manipulation_channels()
        self.statusBar().showMessage(f"Deleted channel {channel_idx} from {dataset_id}", 3000)

    def on_channel_duplicated(self, dataset_id: str, channel_idx: int):
        """Create a new dataset with just this channel's data."""
        sensor_data = self.datasets.get(dataset_id)
        if sensor_data is None:
            return

        ch_name = sensor_data.channel_names[channel_idx]
        new_data = sensor_data.data[:, channel_idx:channel_idx + 1].copy()
        new_name = f"{ch_name} (copy)"
        new_dataset_id = f"{dataset_id}:{ch_name}_copy"
        counter = 2
        base_id = new_dataset_id
        while new_dataset_id in self.datasets:
            new_dataset_id = f"{base_id}_{counter}"
            counter += 1

        new_sd = SensorData(
            timestamps=sensor_data.timestamps.copy(),
            data=new_data,
            sample_rate=sensor_data.sample_rate,
            channel_names=[new_name],
            filename=sensor_data.filename,
        )
        self.datasets[new_dataset_id] = new_sd
        self.timeseries_widget.add_dataset(new_dataset_id, new_sd, 'separate', None)
        self.data_mgmt_panel.refresh(
            self.timeseries_widget.plot_boxes,
            self.timeseries_widget.datasets,
        )
        self._refresh_manipulation_channels()
        self.statusBar().showMessage(
            f"Duplicated '{ch_name}' as new dataset '{new_dataset_id}'",
            3000,
        )

    def on_box_deleted(self, box_name: str):
        """Remove a display box from the time series view."""
        box = self.timeseries_widget._find_plot_box(box_name)
        if box is None:
            return
        self.timeseries_widget.remove_box(box)
        self.data_mgmt_panel.refresh(
            self.timeseries_widget.plot_boxes,
            self.timeseries_widget.datasets,
        )
        self.statusBar().showMessage(f"Removed box '{box_name}'", 2000)

    def on_box_duplicated(self, box_name: str):
        """Duplicate a display box with the same traces."""
        import copy
        src_box = self.timeseries_widget._find_plot_box(box_name)
        if src_box is None:
            return

        from src.widgets.plot_box import PlotBox
        new_box = PlotBox(self.timeseries_widget._next_box_name(),
                          self.timeseries_widget.datasets, self.timeseries_widget)
        for trace in src_box.traces:
            new_box.add_trace(trace['dataset_id'], trace['channel_idx'],
                              trace['color'], trace.get('width', 1.0))
        self.timeseries_widget._add_plot_box(new_box)
        self.timeseries_widget._relink_x_axes()
        self.timeseries_widget._refresh_region_items()
        region = self.timeseries_widget.get_selected_region()
        if region:
            new_box.set_region(*region)
        new_box.get_plot_widget().autoRange()
        self.data_mgmt_panel.refresh(
            self.timeseries_widget.plot_boxes,
            self.timeseries_widget.datasets,
        )
        self.statusBar().showMessage(f"Duplicated box '{box_name}'", 2000)

    def create_menus(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu('&File')

        open_action = QAction('&Open...', self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        load_annotations_action = QAction('Load &Annotations...', self)
        load_annotations_action.setShortcut(QKeySequence('Ctrl+L'))
        load_annotations_action.triggered.connect(self.load_annotations)
        file_menu.addAction(load_annotations_action)

        file_menu.addSeparator()

        load_config_action = QAction('Load C&onfig...', self)
        load_config_action.setShortcut(QKeySequence('Ctrl+Shift+O'))
        load_config_action.triggered.connect(self.load_config_file)
        file_menu.addAction(load_config_action)

        save_config_action = QAction('Save Config &As...', self)
        save_config_action.setShortcut(QKeySequence('Ctrl+Shift+S'))
        save_config_action.triggered.connect(self.save_config_file)
        file_menu.addAction(save_config_action)

        file_menu.addSeparator()

        save_action = QAction('&Save Annotations', self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_annotations)
        file_menu.addAction(save_action)

        export_action = QAction('&Export Annotations...', self)
        export_action.setShortcut(QKeySequence('Ctrl+E'))
        export_action.triggered.connect(self.export_annotations)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        quit_action = QAction('&Quit', self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = menubar.addMenu('&Edit')

        delete_annotation_action = QAction('&Delete Selected Annotation', self)
        delete_annotation_action.setShortcut(QKeySequence.StandardKey.Delete)
        delete_annotation_action.triggered.connect(self.delete_selected_annotation)
        edit_menu.addAction(delete_annotation_action)

        clear_annotations_action = QAction('&Clear All Annotations', self)
        clear_annotations_action.setShortcut(QKeySequence('Ctrl+Shift+D'))
        clear_annotations_action.triggered.connect(self.clear_all_annotations)
        edit_menu.addAction(clear_annotations_action)

        view_menu = menubar.addMenu('&View')

        autoscale_y_action = QAction('Autoscale &Y-Axis', self)
        autoscale_y_action.setShortcut(QKeySequence('Ctrl+Y'))
        autoscale_y_action.triggered.connect(self.autoscale_y_axis)
        view_menu.addAction(autoscale_y_action)

        home_selection_action = QAction('&Home Selection', self)
        home_selection_action.setShortcut(QKeySequence('Ctrl+H'))
        home_selection_action.triggered.connect(self.home_selection)
        view_menu.addAction(home_selection_action)

        tools_menu = menubar.addMenu('&Tools')

        manage_config_action = QAction('&Manage Config...', self)
        manage_config_action.setShortcut(QKeySequence('Ctrl+M'))
        manage_config_action.triggered.connect(self.manage_config)
        tools_menu.addAction(manage_config_action)

        help_menu = menubar.addMenu('&Help')

        feature_ref_action = QAction('&Feature Reference', self)
        feature_ref_action.triggered.connect(self.show_feature_reference)
        help_menu.addAction(feature_ref_action)

        help_menu.addSeparator()

        about_action = QAction('&About', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def delete_selected_annotation(self):
        self.timeseries_widget.delete_selected_annotation()

    def clear_all_annotations(self):
        self.timeseries_widget.clear_all_annotations()
        self.spectrogram_widget.clear_all_annotations()

    def autoscale_y_axis(self):
        self.timeseries_widget.autoscale_y_axis()
        self.spectrogram_widget.autoscale_y_axis()

    def home_selection(self):
        if self.tab_widget.currentIndex() == 0:
            self.timeseries_widget.home_selection()
        elif self.tab_widget.currentIndex() == 1:
            self.spectrogram_widget.home_selection()

    def manage_config(self):
        dialog = ManageConfigDialog(self._enabled_manipulations, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._enabled_manipulations = dialog.get_enabled()
            save_enabled_manipulations(self._enabled_manipulations)
            self.manipulation_panel.set_enabled(self._enabled_manipulations)
            # Sync enabled manipulations to any spatial tab panels
            for entry in self._dynamic_tabs:
                widget = entry['widget']
                if hasattr(widget, 'manip_panel'):
                    widget.manip_panel.set_enabled(self._enabled_manipulations)
            self._refresh_manipulation_channels()

    def _refresh_manipulation_channels(self):
        """Rebuild manipulation panel channel list from current datasets."""
        channel_info = []
        for dataset_id, sensor_data in self.datasets.items():
            for ch_idx, ch_name in enumerate(sensor_data.channel_names):
                channel_info.append((dataset_id, ch_idx, ch_name))
        self.manipulation_panel.refresh_channels(channel_info)
        # Also refresh any spatial tab manipulation panels
        for entry in self._dynamic_tabs:
            widget = entry['widget']
            if hasattr(widget, 'refresh_manip_channels'):
                widget.refresh_manip_channels(self.datasets)

    def on_manipulation_applied(
        self,
        manip_instance,
        channel_idx: int,
        dataset_id: str,
        option_values: dict,
    ):
        """Apply a data manipulation to a channel's data in the current region."""
        sensor_data = self.datasets.get(dataset_id)
        if sensor_data is None:
            QMessageBox.warning(self, "No Data", "Dataset not found.")
            return
        if channel_idx >= sensor_data.n_channels:
            QMessageBox.warning(
                self,
                "Invalid Channel",
                f"Channel {channel_idx} does not exist.",
            )
            return

        region = self.timeseries_widget.get_selected_region()
        if region is None:
            QMessageBox.warning(self, "No Region", "Please select a region first.")
            return

        try:
            # sensor_data.data is (n_samples, n_channels) — use column indexing
            data = sensor_data.data[:, channel_idx].copy()
            new_data = manip_instance.apply(
                data, sensor_data.timestamps, channel_idx, region, option_values
            )
            sensor_data.data[:, channel_idx] = new_data
            self.timeseries_widget.refresh_all_traces()
            self.statusBar().showMessage(
                f"Applied {manip_instance.name} to "
                f"{sensor_data.channel_names[channel_idx]}",
                3000,
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Manipulation Error",
                f"Error applying {manip_instance.name}:\n{str(e)}\n\n{traceback.format_exc()}",
            )

    def on_spatial_manipulation_applied(
        self,
        manip_instance,
        channel_idx: int,
        dataset_id: str,
        option_values: dict,
        spatial_widget,
    ):
        """Apply a manipulation to a channel across the full dataset, then refresh the spatial widget."""
        sensor_data = self.datasets.get(dataset_id)
        if sensor_data is None:
            QMessageBox.warning(self, "No Data", "Dataset not found.")
            return
        if channel_idx >= sensor_data.n_channels:
            QMessageBox.warning(self, "Invalid Channel", f"Channel {channel_idx} does not exist.")
            return

        try:
            data = sensor_data.data[:, channel_idx].copy()
            # Apply over the full time range (no region selection on spatial tab)
            full_region = (float(sensor_data.timestamps[0]), float(sensor_data.timestamps[-1])) \
                if sensor_data.timestamps is not None and len(sensor_data.timestamps) > 0 \
                else (0.0, float(len(data)))
            new_data = manip_instance.apply(
                data, sensor_data.timestamps, channel_idx, full_region, option_values
            )
            sensor_data.data[:, channel_idx] = new_data
            # Refresh spatial widget and timeseries to reflect modified data
            spatial_widget.set_datasets(self.datasets)
            self.timeseries_widget.refresh_all_traces()
            self.statusBar().showMessage(
                f"Applied {manip_instance.name} to "
                f"{sensor_data.channel_names[channel_idx]}",
                3000,
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Manipulation Error",
                f"Error applying {manip_instance.name}:\n{str(e)}\n\n{traceback.format_exc()}",
            )

    def eventFilter(self, obj, event):
        return super().eventFilter(obj, event)

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            'Open Sensor Data File',
            '',
            'Data Files (*.csv *.npy *.h5 *.hdf5);;CSV Files (*.csv);;NumPy Files (*.npy);;HDF5 Files (*.h5 *.hdf5);;All Files (*)'
        )
        if filename:
            self.load_data_file(filename)

    def load_annotations(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            'Load Annotations',
            '',
            'JSON Files (*.json);;All Files (*)'
        )
        if filename:
            self.load_annotations_file(filename)

    def load_annotations_file(self, filename: str):
        try:
            self.statusBar().showMessage(f'Loading annotations from {filename}...')
            loaded_annotations = load_annotations_json(filename)
            if not loaded_annotations:
                QMessageBox.warning(
                    self,
                    'No Annotations',
                    f'No annotations found in {filename}'
                )
                return
            if self.sensor_data:
                for annotation in loaded_annotations:
                    annotation.sample_rate = self.sensor_data.sample_rate
            for annotation in loaded_annotations:
                self.timeseries_widget.annotations.append(annotation)
                self.timeseries_widget.add_annotation_to_plots(annotation)
            self.timeseries_widget.annotations_changed.emit()
            self.statusBar().showMessage(
                f'Loaded {len(loaded_annotations)} annotations from {filename}'
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                'Error Loading Annotations',
                f'Could not load annotations from {filename}:\n\n{str(e)}'
            )
            self.statusBar().showMessage('Error loading annotations')

    def _make_dataset_id(self, filename: str) -> str:
        base_id = os.path.basename(filename)
        if base_id not in self.datasets:
            return base_id
        counter = 2
        while f'{base_id} ({counter})' in self.datasets:
            counter += 1
        return f'{base_id} ({counter})'

    def load_data_file(self, filename: str):
        # ── worker thread so UI stays responsive ──────────────────────────
        result_holder: dict = {}

        class _Loader(QThread):
            finished = _pyqtSignal()
            error = _pyqtSignal(str)

            def run(self_inner):
                try:
                    result_holder['data'] = load_data(filename)
                    self_inner.finished.emit()
                except Exception as exc:
                    result_holder['error'] = str(exc)
                    result_holder['tb'] = traceback.format_exc()
                    self_inner.error.emit(str(exc))

        progress = QProgressDialog(
            f'Loading {os.path.basename(filename)}…', None, 0, 0, self
        )
        progress.setWindowTitle('Loading')
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        loader = _Loader(self)

        def _on_done():
            progress.close()
            self._finish_load(filename, result_holder.get('data'))

        def _on_error(msg):
            progress.close()
            QMessageBox.critical(
                self, 'Error Loading File',
                f'Could not load file:\n{filename}\n\nError: {msg}\n\n{result_holder.get("tb","")}'
            )
            self.statusBar().showMessage('Error loading file')

        loader.finished.connect(_on_done)
        loader.error.connect(_on_error)
        loader.start()
        progress.exec()  # blocks until progress.close() is called

    def _finish_load(self, filename: str, sensor_data):
        if sensor_data is None:
            return
        try:
            if self.config.channel_names:
                sensor_data.apply_channel_names_from_config(self.config.channel_names)

            existing_box_names = self.timeseries_widget.get_plot_boxes()
            dialog = LoadDialog(filename, existing_box_names, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.statusBar().showMessage('Load cancelled', 2000)
                return

            result = dialog.get_result()
            dataset_id = self._make_dataset_id(filename)
            target_box_name = result.get('box_name') if result['action'] == 'existing' else None

            self.timeseries_widget.add_dataset(dataset_id, sensor_data, result['layout'], target_box_name)
            self.datasets[dataset_id] = sensor_data
            self.sensor_data = sensor_data

            info_msg = (f'Loaded: {sensor_data.filename} | '
                        f'{sensor_data.n_samples:,} samples | '
                        f'{sensor_data.n_channels} channels | '
                        f'{sensor_data.duration:.2f}s | '
                        f'{sensor_data.sample_rate:.1f} Hz')
            self.statusBar().showMessage(info_msg)

            self.fft_widget.set_data(sensor_data)
            self.spectrogram_widget.set_data(sensor_data)
            self.fft_panel.update_channel_list(sensor_data.channel_names)
            if self.annotations:
                self.spectrogram_widget.set_annotations(self.annotations)

            self.data_mgmt_panel.refresh(
                self.timeseries_widget.plot_boxes,
                self.timeseries_widget.datasets,
            )
            self._refresh_manipulation_channels()

            selected_region = self.timeseries_widget.get_selected_region()
            if selected_region is not None:
                self.on_region_changed(*selected_region)
        except Exception as e:
            QMessageBox.critical(
                self, 'Error Loading File',
                f'Could not load file:\n{filename}\n\nError: {str(e)}\n\n{traceback.format_exc()}'
            )
            self.statusBar().showMessage('Error loading file')

    def save_annotations(self):
        self.annotations = self.timeseries_widget.get_annotations()
        if not self.annotations:
            QMessageBox.information(
                self,
                'No Annotations',
                'There are no annotations to save.'
            )
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            'Save Annotation Session',
            '',
            'JSON Files (*.json)'
        )
        if filename:
            try:
                sensor_filename = self.sensor_data.filename if self.sensor_data else None
                save_session(self.annotations, filename, sensor_filename)
                self.statusBar().showMessage(f'Saved {len(self.annotations)} annotations to {filename}')
            except Exception as e:
                QMessageBox.critical(
                    self,
                    'Error Saving',
                    f'Could not save annotations:\n{str(e)}'
                )

    def export_annotations(self):
        self.annotations = self.timeseries_widget.get_annotations()
        if not self.annotations:
            QMessageBox.information(
                self,
                'No Annotations',
                'There are no annotations to export.'
            )
            return
        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            'Export Annotations',
            '',
            'JSON Files (*.json);;CSV Files (*.csv)'
        )
        if filename:
            try:
                if selected_filter == 'CSV Files (*.csv)' or filename.endswith('.csv'):
                    export_to_csv(self.annotations, filename)
                else:
                    export_to_json(self.annotations, filename)
                self.statusBar().showMessage(f'Exported {len(self.annotations)} annotations to {filename}')
            except Exception as e:
                QMessageBox.critical(
                    self,
                    'Error Exporting',
                    f'Could not export annotations:\n{str(e)}'
                )

    def show_about(self):
        QMessageBox.about(
            self,
            'About Sensor Data Annotation Tool',
            '<h3>Sensor Data Annotation Tool</h3>'
            '<p>Version 0.1.0</p>'
            '<p>A high-performance tool for annotating time series sensor data '
            'with real-time FFT and STFT visualization.</p>'
            '<p>Built with PyQt6 and PyQtGraph</p>'
        )

    def show_feature_reference(self):
        QMessageBox.information(
            self,
            'Feature Reference - Keyboard Shortcuts',
            '<h3>Keyboard Shortcuts & Features</h3>'
            '<p><b>View & Display:</b></p>'
            '<ul>'
            '<li><b>Ctrl+Y</b> - Autoscale Y-axis to fit visible data (with 5% padding)</li>'
            '<li><b>Ctrl+H</b> - Home Selection - Move selection to 10%-30% of visible segment</li>'
            '</ul>'
            '<p><b>Annotation Management:</b></p>'
            '<ul>'
            '<li><b>Delete</b> - Delete selected annotation</li>'
            '<li><b>Ctrl+Shift+D</b> - Clear all annotations (with confirmation)</li>'
            '</ul>'
            '<p><b>File Operations:</b></p>'
            '<ul>'
            '<li><b>Ctrl+O</b> - Open sensor data file</li>'
            '<li><b>Ctrl+S</b> - Save annotations</li>'
            '<li><b>Ctrl+L</b> - Load annotations from file</li>'
            '<li><b>Ctrl+E</b> - Export annotations to CSV/JSON</li>'
            '<li><b>Ctrl+Shift+O</b> - Load configuration file</li>'
            '<li><b>Ctrl+Shift+S</b> - Save configuration file</li>'
            '</ul>'
            '<p><b>Notes:</b></p>'
            '<ul>'
            '<li>Annotations created in either tab (Time Series or Spectrogram) are automatically synced</li>'
            '<li>All keyboard shortcuts work in both Time Series and Spectrogram tabs</li>'
            '</ul>'
        )

    def on_region_changed(self, start_time: float, end_time: float):
        self.fft_widget.update_fft(start_time, end_time)
        self.spectrogram_widget.set_region(start_time, end_time)

    def on_stft_parameters_changed(self, window_size: int, overlap: float, window_type: str,
                                   use_db: bool, db_ref: float, vmin: float, vmax: float):
        self.spectrogram_widget.set_parameters(window_size, overlap, window_type, use_db, db_ref, vmin, vmax)
        db_info = f'dB scale (range: [{vmin}, {vmax}]dB)' if use_db else 'linear scale'
        self.statusBar().showMessage(
            f'STFT updated: window={window_size}, overlap={overlap*100:.0f}%, '
            f'type={window_type}, {db_info}'
        )

    def on_fft_parameters_changed(self, nperseg: int, window: str):
        self.fft_widget.set_fft_parameters(nperseg, window)
        self.config.fft.nperseg = nperseg
        self.config.fft.window = window
        self.statusBar().showMessage(f'FFT updated: segment size={nperseg}, window={window}', 2000)

    def on_label_selected(self, label_name: str, color: tuple):
        self.current_annotation_label = label_name
        self.timeseries_widget.set_active_label(label_name, color)
        self.statusBar().showMessage(f'Active annotation label: {label_name}')

    def on_annotations_changed(self):
        self.annotations = self.timeseries_widget.get_annotations()
        self.spectrogram_widget.set_annotations(self.annotations)
        self.statusBar().showMessage(f'Total annotations: {len(self.annotations)}')

    def on_annotation_selected(self, annotation):
        if annotation:
            self.statusBar().showMessage(
                f"Selected: '{annotation.label}' ({annotation.start_time:.2f}s - {annotation.end_time:.2f}s) | "
                f'Press Delete key to remove'
            )
        else:
            self.statusBar().showMessage('No annotation selected')

    def on_view_range_changed(self, x_min: float, x_max: float):
        if self.is_syncing_views:
            return
        try:
            self.is_syncing_views = True
            self.spectrogram_widget.set_x_range(x_min, x_max)
        finally:
            self.is_syncing_views = False

    def on_spectrogram_view_range_changed(self, x_min: float, x_max: float):
        if self.is_syncing_views:
            return
        try:
            self.is_syncing_views = True
            if self.timeseries_widget.plot_widgets:
                self.timeseries_widget.is_updating_range = True
                self.timeseries_widget.plot_widgets[0].setXRange(x_min, x_max, padding=0)
                self.timeseries_widget.is_updating_range = False
        finally:
            self.is_syncing_views = False

    def on_spectrogram_annotations_changed(self):
        self.annotations = self.spectrogram_widget.annotations
        self.timeseries_widget.load_annotations(self.annotations)
        self.statusBar().showMessage(f'Total annotations: {len(self.annotations)}')

    def on_spectrogram_region_changed(self, start: float, end: float):
        if self.timeseries_widget and hasattr(self.timeseries_widget, 'region_items'):
            if self.timeseries_widget.region_items:
                for region_item in self.timeseries_widget.region_items:
                    region_item.blockSignals(True)
                    region_item.setRegion([start, end])
                    region_item.blockSignals(False)
                self.timeseries_widget.update_inputs_from_region()
                self.timeseries_widget.region_changed.emit(start, end)

    def start_playback(self, widget):
        if self.is_playing and self.active_playback_widget != widget:
            print(f'[DEBUG] Stopping playback in {self.active_playback_widget.__class__.__name__} before starting in {widget.__class__.__name__}')
            self.active_playback_widget.stop_playback()
        self.active_playback_widget = widget
        return True

    def stop_playback_global(self):
        if self.is_playing and self.active_playback_widget:
            self.active_playback_widget.stop_playback()

    def apply_config(self):
        self.annotation_panel.clear_labels()
        for label_config in self.config.labels:
            self.annotation_panel.add_label(label_config.name, label_config.color)

        self.stft_panel.set_window_size(self.config.stft.window_size)
        self.stft_panel.set_overlap(self.config.stft.overlap)
        self.stft_panel.set_window_type(self.config.stft.window_type)
        self.stft_panel.set_db_transform(
            self.config.stft.use_db,
            self.config.stft.db_ref,
            self.config.stft.vmin,
            self.config.stft.vmax
        )

        self.fft_panel.set_fft_parameters(self.config.fft.nperseg, self.config.fft.window)
        self.fft_widget.set_fft_parameters(self.config.fft.nperseg, self.config.fft.window)

        if self.config.channel_names:
            for sensor_data in self.datasets.values():
                sensor_data.apply_channel_names_from_config(self.config.channel_names)
            self.timeseries_widget.refresh_all_traces()
            if self.sensor_data:
                self.fft_widget.set_data(self.sensor_data)
                self.spectrogram_widget.set_data(self.sensor_data)
                if self.annotations:
                    self.spectrogram_widget.set_annotations(self.annotations)
                self.fft_panel.update_channel_list(self.sensor_data.channel_names)
            self._refresh_manipulation_channels()

        if self.sensor_data:
            self.on_stft_parameters_changed(
                self.config.stft.window_size,
                self.config.stft.overlap,
                self.config.stft.window_type,
                self.config.stft.use_db,
                self.config.stft.db_ref,
                self.config.stft.vmin,
                self.config.stft.vmax
            )

        if self.config.enabled_manipulations:
            self._enabled_manipulations = list(self.config.enabled_manipulations)
            save_enabled_manipulations(self._enabled_manipulations)
            self.manipulation_panel.set_enabled(self._enabled_manipulations)
            self._refresh_manipulation_channels()

        if self.config.loaded_files:
            for file_cfg in self.config.loaded_files:
                if file_cfg.dataset_id in self.datasets:
                    continue
                if not os.path.exists(file_cfg.path):
                    self.statusBar().showMessage(
                        f'File not found (skipped): {file_cfg.path}',
                        3000,
                    )
                    continue
                try:
                    sensor_data = load_data(file_cfg.path)
                    if file_cfg.channel_names:
                        for i, name in enumerate(file_cfg.channel_names):
                            if i < len(sensor_data.channel_names):
                                sensor_data.channel_names[i] = name
                    dataset_id = file_cfg.dataset_id
                    if dataset_id in self.datasets:
                        dataset_id = self._make_dataset_id(file_cfg.path)
                    self.timeseries_widget.add_dataset(dataset_id, sensor_data, 'separate', None)
                    self.datasets[dataset_id] = sensor_data
                    self.sensor_data = sensor_data
                    self.fft_widget.set_data(sensor_data)
                    self.spectrogram_widget.set_data(sensor_data)
                    self.fft_panel.update_channel_list(sensor_data.channel_names)
                    self.data_mgmt_panel.refresh(
                        self.timeseries_widget.plot_boxes,
                        self.timeseries_widget.datasets,
                    )
                    self._refresh_manipulation_channels()
                except Exception as e:
                    self.statusBar().showMessage(
                        f'Error reloading {file_cfg.path}: {e}',
                        3000,
                    )

    def load_config_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            'Load Configuration',
            '',
            'JSON Files (*.json);;All Files (*)'
        )
        if filename:
            try:
                self.config = AppConfig.load(filename)
                self.apply_config()
                self.statusBar().showMessage('? Configuration loaded successfully', 2000)
            except FileNotFoundError:
                self.statusBar().showMessage(f'? Configuration file not found: {filename}', 2000)
            except Exception as e:
                self.statusBar().showMessage(f'? Error loading configuration: {str(e)}', 2000)

    def save_config_file(self):
        self.update_config_from_widgets()
        filename, _ = QFileDialog.getSaveFileName(
            self,
            'Save Configuration',
            'config.json',
            'JSON Files (*.json);;All Files (*)'
        )
        if filename:
            try:
                self.config.save(filename)
                self.statusBar().showMessage(f'Configuration saved to {filename}', 3000)
                QMessageBox.information(
                    self,
                    'Config Saved',
                    f'Configuration successfully saved to:\n{filename}'
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    'Error',
                    f'Error saving configuration:\n{str(e)}'
                )

    def update_config_from_widgets(self):
        self.config.labels = []
        for name, color in self.annotation_panel.get_all_labels():
            from src.utils.config import LabelConfig
            self.config.labels.append(LabelConfig(name, color))

        params = self.stft_panel.get_all_parameters()
        self.config.stft.window_size = params['window_size']
        self.config.stft.overlap = params['overlap']
        self.config.stft.window_type = params['window_type']
        self.config.stft.use_db = params['use_db']
        self.config.stft.db_ref = params['db_ref']
        self.config.stft.vmin = params['vmin']
        self.config.stft.vmax = params['vmax']

        fft_nperseg, fft_window = self.fft_panel.get_fft_parameters()
        self.config.fft.nperseg = fft_nperseg
        self.config.fft.window = fft_window

        if self.sensor_data:
            self.config.channel_names = list(self.sensor_data.channel_names)

        from src.utils.config import LoadedFileConfig, ManipulationOptionConfig

        self.config.loaded_files = []
        for dataset_id, sensor_data in self.datasets.items():
            if sensor_data.filename:
                self.config.loaded_files.append(LoadedFileConfig(
                    path=sensor_data.filename,
                    dataset_id=dataset_id,
                    channel_names=list(sensor_data.channel_names),
                ))

        self.config.manipulations = []
        self.config.enabled_manipulations = list(self._enabled_manipulations)
        for name in self._enabled_manipulations:
            self.config.manipulations.append(
                ManipulationOptionConfig(name=name, options={})
            )
