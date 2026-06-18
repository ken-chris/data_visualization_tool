# Annotation Guide

## Overview

The Time Series tab supports drag-to-create labeled time region annotations, with full edit and export support.

## Creating Annotations

1. Open the **Annotation Labels** section in the left sidebar (Time Series tab)
2. Click **Add Label**, enter a name, and pick a color
3. Click a label in the list to make it **active** (highlighted)
4. On any plot, drag the blue **region selector** to cover the time span you want
5. Click **Create Annotation from Region** — the region appears as a colored overlay on all plots

## Managing Labels

| Action | How |
|--------|-----|
| Add label | Click **Add Label**, enter name |
| Rename label | Double-click the label in the list |
| Change color | Select label, click **Change Color** |
| Remove label | Select label, click **Remove Label** |
| Set active label | Click the label row |

## Editing Annotations

- **Resize**: drag the left or right edge of any annotation overlay
- **Edit notes**: right-click the annotation → **Edit**
- **Delete**: right-click → **Delete Annotation**
- All channels display the same annotations, synchronized

## Overlap Detection

If you try to create an annotation that overlaps an existing one, the app warns you. You can proceed or cancel.

## Exporting Annotations

**File → Export Annotations** (`Ctrl+E`)

Choose JSON or CSV format. Each exported annotation includes:
- Label name and color
- Start and end time (seconds)
- Duration
- Notes (if any)

### JSON format
```json
[
  {
    "label": "Walking",
    "color": [255, 0, 0],
    "start": 1.25,
    "end": 3.80,
    "duration": 2.55,
    "notes": ""
  }
]
```

### CSV format
```
label,color,start,end,duration,notes
Walking,"[255, 0, 0]",1.25,3.8,2.55,
```

## Saving and Loading Sessions

**File → Save Session** (`Ctrl+S`) saves both the data references and all annotations to a JSON session file.

**File → Load Session** restores a previously saved session.


### 5. **Export Annotations**
Use **File → Export Annotations** to save your work:
- **JSON format**: Structured data with all annotation details
- **CSV format**: Spreadsheet-compatible for analysis

### 6. **Save/Load Sessions**
- **File → Save Session**: Save annotations with data file reference
- **File → Load Session**: Restore annotations from a previous session

## Workflow Example

1. **Load Data**: File → Open → Select sensor data file
2. **Set Up Labels**:
   - Add labels like "Walking", "Running", "Resting"
   - Assign distinct colors to each
3. **Annotate**:
   - Select "Walking" label
   - Drag region selector to walking period (e.g., 0-5 seconds)
   - Click "Create Annotation from Region"
   - Repeat for other activities
4. **Review**:
   - Switch between Time Series, Spectrogram, and FFT tabs
   - Annotations remain visible across views
5. **Export**:
   - File → Export Annotations → Choose JSON or CSV
   - Use annotations in your analysis pipeline

## Keyboard Shortcuts

- **Ctrl+O**: Open data file
- **Ctrl+S**: Save annotation session
- **Ctrl+E**: Export annotations

## Tips

- **Multi-Channel**: Annotations span all channels - useful for whole-sensor events
- **Visual Distinction**: Use high-contrast colors for easy identification
- **Notes Field**: Add detailed observations for each annotation
- **CSV Export**: Perfect for importing into pandas/Excel for statistical analysis
- **JSON Export**: Preserves all metadata including notes and precise timestamps

## Annotation Data Format

### JSON Export Structure
```json
{
  "annotations": [
    {
      "label": "Walking",
      "start_time": 0.0,
      "end_time": 5.2,
      "duration": 5.2,
      "color": [255, 0, 0],
      "notes": "Normal walking pace"
    }
  ],
  "metadata": {
    "sensor_data_file": "sample_data_3ch.csv",
    "n_annotations": 1,
    "export_timestamp": "2024-01-15T10:30:00"
  }
}
```

### CSV Export Structure
```csv
label,start_time,end_time,duration,notes
Walking,0.0,5.2,5.2,Normal walking pace
Running,5.2,10.5,5.3,Sprint interval
```

## Technical Details

### Implementation
- **Time Series Widget**: Manages annotation regions using PyQtGraph LinearRegionItem
- **Annotation Model**: Dataclass with start/end times, label, color, notes
- **Synchronization**: All channels display the same annotations with matching colors
- **Export Utilities**: JSON and CSV formatters in `src/utils/export.py`

### Annotation Storage
- Annotations stored in memory during session
- Export saves to disk in structured format
- Load session restores annotations from saved file

### Visual Representation
- Each annotation = LinearRegionItem overlay on time series plots
- Semi-transparent fill (80/255 alpha) for visibility
- Colored border (2px width) matches label color
- Movable/resizable with mouse drag

## Troubleshooting

**Annotations not appearing?**
- Ensure data is loaded first (File → Open)
- Check that the time range is visible in the plot
- Try zooming out to see the full timeline

**Can't create annotation?**
- Select an annotation label from the panel first
- Ensure region selector has valid start < end times
- Check for overlap warnings and respond accordingly

**Export failing?**
- Verify you have write permissions in the target directory
- Ensure filename has correct extension (.json or .csv)
- Check that annotations exist (at least one created)

## Future Enhancements
- [ ] Batch annotation from CSV template
- [ ] Annotation validation rules
- [ ] Auto-annotation using ML models
- [ ] Collaborative annotation (multi-user)
- [ ] Annotation statistics dashboard
