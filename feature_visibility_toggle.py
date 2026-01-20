"""
Main plugin class for Feature Visibility Toggle
"""
from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QDockWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QPushButton, QLabel, QAction, QMessageBox, QSplitter,
    QDialog, QHBoxLayout, QCheckBox, QListWidget, QListWidgetItem, QScrollArea,
    QGroupBox, QDialogButtonBox, QSpinBox, QFormLayout, QLineEdit, QComboBox
)
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsLayerTreeLayer,
    QgsLayerTreeGroup,
    QgsFeature,
    QgsFeatureRequest
)
from qgis.gui import QgsLayerTreeView

# Don't import problematic classes for now
# from .feature_tree_proxy import FeatureTreeProxyModel
# from .feature_node import FeatureNode


class SettingsDialog(QDialog):
    """Settings dialog for selecting attributes to display per layer."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Show/Hide Each Element Panel Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        
        self.layer_attributes = {}  # layer_id -> [list of selected attribute names]
        
        layout = QVBoxLayout(self)
        
        # General settings section
        general_group = QGroupBox("General Settings")
        general_layout = QFormLayout()
        
        # Feature limit setting
        self.feature_limit_spin = QSpinBox()
        self.feature_limit_spin.setMinimum(0)
        self.feature_limit_spin.setMaximum(1000000)
        self.feature_limit_spin.setValue(0)  # 0 means no limit
        self.feature_limit_spin.setSpecialValueText("No limit")
        self.feature_limit_spin.setToolTip("Maximum number of features to display in the panel (0 = no limit)")
        general_layout.addRow("Max features to display:", self.feature_limit_spin)
        
        general_group.setLayout(general_layout)
        layout.addWidget(general_group)
        
        # Layer attributes section
        attributes_label = QLabel("Select attributes to display for each layer:")
        layout.addWidget(attributes_label)
        
        # Tree widget for collapsible layers
        self.layers_tree = QTreeWidget()
        self.layers_tree.setHeaderLabel("Layers")
        self.layers_tree.setRootIsDecorated(True)
        self.layers_tree.setAlternatingRowColors(True)
        
        # Get all vector layers
        layers = []
        for layer_id, layer in QgsProject.instance().mapLayers().items():
            if isinstance(layer, QgsVectorLayer):
                layers.append((layer.name(), layer_id, layer))
        
        # Sort by name
        layers.sort(key=lambda x: x[0])
        
        for layer_name, layer_id, layer in layers:
            # Create parent item for layer
            layer_item = QTreeWidgetItem(self.layers_tree, [layer_name])
            layer_item.setExpanded(False)  # Start collapsed
            layer_item.setData(0, Qt.UserRole, layer_id)
            
            # Get all fields except visibility field
            fields = layer.fields()
            checkboxes = {}
            filters = {}  # field_name -> {'type': combo, 'value': line_edit}
            
            for field in fields:
                if field.name() != "_fvt_vis":
                    # Create child item for field
                    field_item = QTreeWidgetItem(layer_item, [""])
                    
                    # Create widget for field row with checkbox and filters
                    field_widget = QWidget()
                    field_row = QHBoxLayout(field_widget)
                    field_row.setContentsMargins(2, 2, 2, 2)
                    
                    # Checkbox for display
                    cb = QCheckBox(field.name())
                    checkboxes[field.name()] = cb
                    field_row.addWidget(cb)
                    
                    # Filter type dropdown
                    filter_type = QComboBox()
                    filter_type.addItems(["No filter", "Contains", "Equals", "Starts with", "Ends with", "Greater than", "Less than"])
                    filter_type.setMaximumWidth(120)
                    
                    # Filter value input
                    filter_value = QLineEdit()
                    filter_value.setPlaceholderText("Filter value...")
                    filter_value.setMaximumWidth(150)
                    
                    # Store filter widgets
                    filters[field.name()] = {
                        'type': filter_type,
                        'value': filter_value
                    }
                    
                    field_row.addWidget(QLabel("Filter:"))
                    field_row.addWidget(filter_type)
                    field_row.addWidget(filter_value)
                    field_row.addStretch()
                    
                    # Set widget for the tree item
                    self.layers_tree.setItemWidget(field_item, 0, field_widget)
            
            self.layer_attributes[layer_id] = {
                'checkboxes': checkboxes,
                'filters': filters,
                'layer': layer
            }
        
        layout.addWidget(self.layers_tree)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Help)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.helpRequested.connect(self.show_help)
        layout.addWidget(button_box)
    
    def get_selected_attributes(self):
        """Get selected attributes for each layer."""
        result = {}
        for layer_id, data in self.layer_attributes.items():
            selected = []
            for attr_name, checkbox in data['checkboxes'].items():
                if checkbox.isChecked():
                    selected.append(attr_name)
            result[layer_id] = selected
        return result
    
    def set_selected_attributes(self, layer_attributes):
        """Set selected attributes for each layer."""
        for layer_id, selected_attrs in layer_attributes.items():
            if layer_id in self.layer_attributes:
                for attr_name, checkbox in self.layer_attributes[layer_id]['checkboxes'].items():
                    checkbox.setChecked(attr_name in selected_attrs)
    
    def get_filters(self):
        """Get filters for each layer and field."""
        result = {}
        for layer_id, data in self.layer_attributes.items():
            layer_filters = {}
            for field_name, filter_widgets in data['filters'].items():
                filter_type = filter_widgets['type'].currentText()
                filter_value = filter_widgets['value'].text().strip()
                if filter_type != "No filter" and filter_value:
                    layer_filters[field_name] = {
                        'type': filter_type,
                        'value': filter_value
                    }
            if layer_filters:
                result[layer_id] = layer_filters
        return result
    
    def set_filters(self, filters):
        """Set filters for each layer and field."""
        for layer_id, layer_filters in filters.items():
            if layer_id in self.layer_attributes:
                for field_name, filter_data in layer_filters.items():
                    if field_name in self.layer_attributes[layer_id]['filters']:
                        filter_widgets = self.layer_attributes[layer_id]['filters'][field_name]
                        filter_type = filter_data.get('type', 'No filter')
                        filter_value = filter_data.get('value', '')
                        
                        # Set filter type
                        index = filter_widgets['type'].findText(filter_type)
                        if index >= 0:
                            filter_widgets['type'].setCurrentIndex(index)
                        else:
                            filter_widgets['type'].setCurrentIndex(0)  # No filter
                        
                        # Set filter value
                        filter_widgets['value'].setText(filter_value)
    
    def get_feature_limit(self):
        """Get the feature display limit."""
        return self.feature_limit_spin.value()
    
    def set_feature_limit(self, limit):
        """Set the feature display limit."""
        self.feature_limit_spin.setValue(limit)
    
    def show_help(self):
        """Show help dialog with usage instructions."""
        help_text = """<h3>Quick Help - Show/Hide Each Element Panel</h3>

<p><b>Main Panel:</b></p>
<p>• Click a layer in "Layers" to see its features<br>
• Check/uncheck features to show/hide them on map<br>
• Selected layer shows ✓ mark<br>
• Drag divider to resize panels</p>

<p><b>Settings (⚙ button):</b></p>
<p>• <b>Max features:</b> Limit how many features display (0 = no limit)<br>
• <b>Attributes:</b> Check fields to display as columns<br>
• <b>Filters:</b> Only works for checked fields<br>
&nbsp;&nbsp;- Contains/Equals/Starts with/Ends with: Text matching<br>
&nbsp;&nbsp;- Greater/Less than: Number comparison<br>
• Expand layers to see their fields</p>

<p><b>Tips:</b></p>
<p>• Filters apply only to checked (displayed) fields<br>
• Multiple filters = all must match<br>
• Settings are saved automatically</p>

<p><b>For further help:</b></p>
<p>• Contact: kk.at.work@pm.me</p>"""
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Plugin Help")
        msg.setTextFormat(Qt.RichText)
        msg.setText(help_text)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()


class FeatureVisibilityToggle:
    """QGIS Plugin Implementation"""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        self.iface = iface
        self.dock_widget = None
        self.feature_visibility = {}  # layer_id -> {feature_id: visible}
        self.action = None
        self.enabled = False
        self.layer_attributes = {}  # layer_id -> [list of attribute names to display]
        self.layer_filters = {}  # layer_id -> {field_name: {'type': str, 'value': str}}
        self.feature_limit = 0  # 0 means no limit
        self.settings = QSettings()
        self.current_layer_item = None  # Currently selected layer item in the tree
        self.layer_item_names = {}  # Store original layer names: layer_id -> original_name

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        try:
            # Create action that will enable the plugin functionality
            self.action = QAction(
                QIcon(),
                "Show/Hide Each Element Panel",
                self.iface.mainWindow()
            )
            self.action.triggered.connect(self.show_dock_widget)
            self.action.setToolTip("Show/Hide Each Element Panel")
            
            # Add toolbar button and menu item
            self.iface.addToolBarIcon(self.action)
            self.iface.addPluginToMenu("Show/Hide Each Element Panel", self.action)
        except Exception as e:
            print(f"ERROR in initGui: {e}")
            import traceback
            traceback.print_exc()

    def show_dock_widget(self):
        """Show/hide the feature visibility dock widget (toggle)."""
        try:
            if self.dock_widget is None:
                self.create_dock_widget()
            
            if self.dock_widget:
                if self.dock_widget.isVisible():
                    self.dock_widget.hide()
                else:
                    self.dock_widget.show()
                    self.dock_widget.raise_()
        except Exception as e:
            print(f"ERROR showing dock widget: {e}")
            import traceback
            traceback.print_exc()
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.warning(None, "Plugin Error", f"Error showing panel:\n{str(e)}")
    
    def create_dock_widget(self):
        """Create the dock widget for feature visibility toggles."""
        try:
            print("Creating dock widget...")
            
            # Create dock widget
            self.dock_widget = QDockWidget("Show/Hide Each Element Panel", self.iface.mainWindow())
            self.dock_widget.setObjectName("FeatureVisibilityToggleDock")
            
            # Create main widget
            main_widget = QWidget()
            layout = QVBoxLayout(main_widget)
            
            # Top row with label and settings button
            top_row = QHBoxLayout()
            label = QLabel("Select a layer to toggle feature visibility:")
            top_row.addWidget(label)
            top_row.addStretch()
            
            # Settings button with cog icon
            settings_btn = QPushButton("⚙")
            settings_btn.setToolTip("Settings")
            settings_btn.setMaximumWidth(30)
            settings_btn.clicked.connect(self.show_settings)
            top_row.addWidget(settings_btn)
            layout.addLayout(top_row)
            
            # Add refresh button
            refresh_btn = QPushButton("Refresh Layers")
            refresh_btn.clicked.connect(self.refresh_layers)
            layout.addWidget(refresh_btn)
            
            # Create splitter for resizable layers and features panels
            splitter = QSplitter(Qt.Vertical)
            
            # Create tree widget for layers
            self.layer_tree = QTreeWidget()
            self.layer_tree.setHeaderLabel("Layers")
            self.layer_tree.itemClicked.connect(self.on_layer_selected)
            splitter.addWidget(self.layer_tree)
            
            # Create tree widget for features (will be populated when layer is selected)
            self.feature_tree = QTreeWidget()
            self.feature_tree.setHeaderLabel("Features")
            splitter.addWidget(self.feature_tree)
            
            # Set initial sizes (50/50 split)
            splitter.setSizes([200, 200])
            
            layout.addWidget(splitter)
            
            self.dock_widget.setWidget(main_widget)
            
            # Add to QGIS
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
            
            # Connect to project signals
            QgsProject.instance().layersAdded.connect(self.refresh_layers)
            QgsProject.instance().layersRemoved.connect(self.refresh_layers)
            
            # Initial refresh
            self.refresh_layers()
            
            # Load settings
            self.load_settings()
            
            print("Dock widget created successfully!")
        except Exception as e:
            print(f"ERROR creating dock widget: {e}")
            import traceback
            traceback.print_exc()
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.warning(None, "Plugin Error", f"Error creating panel:\n{str(e)}")
    
    def refresh_layers(self):
        """Refresh the layer list in the dock widget."""
        try:
            if not self.layer_tree:
                return
            
            self.layer_tree.clear()
            self.layer_item_names.clear()
            # Clear current layer item reference
            self.current_layer_item = None
            
            root = QgsProject.instance().layerTreeRoot()
            if not root:
                return
            
            def add_layers(node, parent_item):
                for child in node.children():
                    if isinstance(child, QgsLayerTreeLayer):
                        layer = child.layer()
                        if isinstance(layer, QgsVectorLayer):
                            layer_name = layer.name()
                            item = QTreeWidgetItem(parent_item, [layer_name])
                            item.setData(0, Qt.UserRole, layer.id())
                            # Store original name
                            self.layer_item_names[layer.id()] = layer_name
                    elif isinstance(child, QgsLayerTreeGroup):
                        group_item = QTreeWidgetItem(parent_item, [child.name()])
                        add_layers(child, group_item)
            
            add_layers(root, self.layer_tree)
            self.layer_tree.expandAll()
        except Exception as e:
            print(f"ERROR refreshing layers: {e}")
            import traceback
            traceback.print_exc()
    
    def on_layer_selected(self, item, column):
        """Handle layer selection in the tree."""
        try:
            layer_id = item.data(0, Qt.UserRole)
            if not layer_id:
                return
            
            layer = QgsProject.instance().mapLayer(layer_id)
            if not isinstance(layer, QgsVectorLayer):
                return
            
            # Remove checkmark from previously selected layer
            if self.current_layer_item and self.current_layer_item != item:
                prev_layer_id = self.current_layer_item.data(0, Qt.UserRole)
                if prev_layer_id and prev_layer_id in self.layer_item_names:
                    original_name = self.layer_item_names[prev_layer_id]
                    self.current_layer_item.setText(0, original_name)
            
            # Add checkmark to currently selected layer
            self.current_layer_item = item
            original_name = self.layer_item_names.get(layer_id, layer.name())
            item.setText(0, f"✓ {original_name}")
            
            # Create/ensure visibility field exists
            self.ensure_visibility_field(layer)
            
            # Disconnect signal temporarily to avoid triggering during population
            try:
                self.feature_tree.itemChanged.disconnect(self.on_feature_checkbox_changed)
            except:
                pass
            
            # Populate features
            self.feature_tree.clear()
            self.feature_tree.setHeaderLabel(f"Features: {layer.name()}")
            
            # Initialize visibility state if needed - get ALL features first
            if layer_id not in self.feature_visibility:
                self.feature_visibility[layer_id] = {}
            
            # Get visibility field index
            vis_field_idx = layer.fields().indexOf("_fvt_vis")
            
            # Get selected attributes for this layer
            selected_attrs = self.layer_attributes.get(layer_id, [])
            
            # Get filters for this layer (only for checked fields)
            layer_filters = self.layer_filters.get(layer_id, {})
            # Only apply filters for fields that are checked/selected
            active_filters = {field: filters for field, filters in layer_filters.items() if field in selected_attrs}
            
            # First, get all features and their current visibility state
            features_data = []
            feature_limit = self.feature_limit if self.feature_limit > 0 else None
            
            for feature in layer.getFeatures():
                fid = feature.id()
                
                # Apply filters - skip feature if it doesn't match (only for checked fields)
                if not self.feature_matches_filters(feature, layer, active_filters):
                    continue
                
                # Get current visibility from field (default: 1 = visible)
                if vis_field_idx >= 0:
                    vis_value = feature.attribute(vis_field_idx)
                    is_visible = vis_value is not None and vis_value != 0
                else:
                    is_visible = True
                
                # Store in our tracking dict
                if fid not in self.feature_visibility[layer_id]:
                    self.feature_visibility[layer_id][fid] = is_visible
                
                features_data.append((fid, feature, is_visible))
                
                # Apply feature limit if set
                if feature_limit and len(features_data) >= feature_limit:
                    break
            
            # Set up feature tree headers (with limit info if applicable)
            if feature_limit:
                total_count = layer.featureCount()
                limit_text = f"Features (showing {len(features_data)} of {total_count})"
                if selected_attrs:
                    headers = [limit_text] + selected_attrs
                    self.feature_tree.setHeaderLabels(headers)
                    self.feature_tree.setColumnCount(len(headers))
                else:
                    self.feature_tree.setHeaderLabel(limit_text)
                    self.feature_tree.setColumnCount(1)
            else:
                if selected_attrs:
                    headers = ["Feature"] + selected_attrs
                    self.feature_tree.setHeaderLabels(headers)
                    self.feature_tree.setColumnCount(len(headers))
                else:
                    self.feature_tree.setHeaderLabel("Features")
                    self.feature_tree.setColumnCount(1)
            
            # Now add features to tree
            for fid, feature, is_visible in features_data:
                
                # Create display text
                if selected_attrs:
                    display_parts = [f"Feature {fid}"]
                    for attr_name in selected_attrs:
                        attr_idx = layer.fields().indexOf(attr_name)
                        if attr_idx >= 0:
                            value = feature.attribute(attr_idx)
                            display_parts.append(str(value) if value is not None else "")
                        else:
                            display_parts.append("")
                    feature_item = QTreeWidgetItem(self.feature_tree, display_parts)
                else:
                    feature_item = QTreeWidgetItem(self.feature_tree, [f"Feature {fid}"])
                
                # Set checkbox only in first column
                feature_item.setCheckState(0, Qt.Checked if is_visible else Qt.Unchecked)
                feature_item.setFlags(feature_item.flags() | Qt.ItemIsUserCheckable)
                feature_item.setData(0, Qt.UserRole, (layer_id, fid))
            
            # Reconnect signal for checkbox changes
            self.feature_tree.itemChanged.connect(self.on_feature_checkbox_changed)
            
            # Update layer visibility based on current state
            self.update_layer_visibility(layer)
        except Exception as e:
            print(f"ERROR selecting layer: {e}")
            import traceback
            traceback.print_exc()
    
    def feature_matches_filters(self, feature, layer, filters):
        """Check if a feature matches all the specified filters."""
        if not filters:
            return True
        
        for field_name, filter_data in filters.items():
            filter_type = filter_data.get('type', 'Contains')
            filter_value = filter_data.get('value', '').strip()
            
            if not filter_value:
                continue
            
            # Get field index
            field_idx = layer.fields().indexOf(field_name)
            if field_idx < 0:
                continue
            
            # Get feature value
            feature_value = feature.attribute(field_idx)
            if feature_value is None:
                feature_value_str = ""
            else:
                feature_value_str = str(feature_value).lower()
            
            filter_value_lower = filter_value.lower()
            
            # Apply filter based on type
            matches = False
            if filter_type == "Contains":
                matches = filter_value_lower in feature_value_str
            elif filter_type == "Equals":
                matches = feature_value_str == filter_value_lower
            elif filter_type == "Starts with":
                matches = feature_value_str.startswith(filter_value_lower)
            elif filter_type == "Ends with":
                matches = feature_value_str.endswith(filter_value_lower)
            elif filter_type == "Greater than":
                try:
                    feature_num = float(feature_value) if feature_value is not None else 0
                    filter_num = float(filter_value)
                    matches = feature_num > filter_num
                except (ValueError, TypeError):
                    matches = False
            elif filter_type == "Less than":
                try:
                    feature_num = float(feature_value) if feature_value is not None else 0
                    filter_num = float(filter_value)
                    matches = feature_num < filter_num
                except (ValueError, TypeError):
                    matches = False
            
            # If any filter doesn't match, feature is excluded
            if not matches:
                return False
        
        # All filters matched
        return True
    
    def on_feature_checkbox_changed(self, item, column):
        """Handle feature checkbox change."""
        try:
            data = item.data(0, Qt.UserRole)
            if not data:
                return
            
            layer_id, feature_id = data
            visible = item.checkState(0) == Qt.Checked
            
            if layer_id not in self.feature_visibility:
                self.feature_visibility[layer_id] = {}
            
            self.feature_visibility[layer_id][feature_id] = visible
            
            # Update the visibility field in the layer
            layer = QgsProject.instance().mapLayer(layer_id)
            if isinstance(layer, QgsVectorLayer):
                self.update_feature_visibility_field(layer, feature_id, visible)
                self.update_layer_visibility(layer)
        except Exception as e:
            print(f"ERROR changing feature visibility: {e}")
            import traceback
            traceback.print_exc()
    
    def show_settings(self):
        """Show settings dialog."""
        try:
            dialog = SettingsDialog(self.iface.mainWindow())
            
            # Load current settings into dialog
            dialog.set_selected_attributes(self.layer_attributes)
            dialog.set_feature_limit(self.feature_limit)
            dialog.set_filters(self.layer_filters)
            
            if dialog.exec_() == QDialog.Accepted:
                # Save settings
                self.layer_attributes = dialog.get_selected_attributes()
                self.feature_limit = dialog.get_feature_limit()
                self.layer_filters = dialog.get_filters()
                self.save_settings()
                
                # Refresh current layer display if a layer is selected
                if self.feature_tree and self.feature_tree.topLevelItemCount() > 0:
                    # Find currently selected layer
                    selected_items = self.layer_tree.selectedItems()
                    if selected_items:
                        self.on_layer_selected(selected_items[0], 0)
        except Exception as e:
            print(f"ERROR showing settings: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(None, "Settings Error", f"Error opening settings:\n{str(e)}")
    
    def load_settings(self):
        """Load attribute display settings from QSettings."""
        try:
            self.settings.beginGroup("FeatureVisibilityToggle")
            
            # Load feature limit
            self.feature_limit = self.settings.value("featureLimit", 0, type=int)
            
            # Load layer attributes and filters
            layer_ids = self.settings.childGroups()
            for layer_id in layer_ids:
                if layer_id == "featureLimit":  # Skip the featureLimit key
                    continue
                self.settings.beginGroup(layer_id)
                
                # Load attributes
                attrs_str = self.settings.value("attributes", "")
                if attrs_str:
                    attrs_list = attrs_str.split(",") if attrs_str else []
                    self.layer_attributes[layer_id] = attrs_list
                
                # Load filters
                filters_str = self.settings.value("filters", "")
                if filters_str:
                    # Filters are stored as: "field1:type1:value1|field2:type2:value2"
                    layer_filters = {}
                    filter_parts = filters_str.split("|")
                    for filter_part in filter_parts:
                        if ":" in filter_part:
                            parts = filter_part.split(":", 2)
                            if len(parts) >= 3:
                                # Unescape special characters
                                field_name = parts[0].replace("_COLON_", ":").replace("_PIPE_", "|")
                                filter_type = parts[1].replace("_COLON_", ":").replace("_PIPE_", "|")
                                filter_value = parts[2].replace("_COLON_", ":").replace("_PIPE_", "|")
                                layer_filters[field_name] = {
                                    'type': filter_type,
                                    'value': filter_value
                                }
                    if layer_filters:
                        self.layer_filters[layer_id] = layer_filters
                
                self.settings.endGroup()
            
            self.settings.endGroup()
        except Exception as e:
            print(f"ERROR loading settings: {e}")
            import traceback
            traceback.print_exc()
    
    def save_settings(self):
        """Save attribute display settings to QSettings."""
        try:
            self.settings.beginGroup("FeatureVisibilityToggle")
            
            # Save feature limit
            self.settings.setValue("featureLimit", self.feature_limit)
            
            # Clear old layer settings
            layer_ids = self.settings.childGroups()
            for layer_id in layer_ids:
                if layer_id != "featureLimit":
                    self.settings.remove(layer_id)
            
            # Save new layer attribute settings and filters
            for layer_id, attrs_list in self.layer_attributes.items():
                self.settings.beginGroup(layer_id)
                self.settings.setValue("attributes", ",".join(attrs_list))
                
                # Save filters for this layer
                if layer_id in self.layer_filters:
                    filters_parts = []
                    for field_name, filter_data in self.layer_filters[layer_id].items():
                        # Escape special characters
                        field_escaped = field_name.replace(":", "_COLON_").replace("|", "_PIPE_")
                        type_escaped = filter_data['type'].replace(":", "_COLON_").replace("|", "_PIPE_")
                        value_escaped = filter_data['value'].replace(":", "_COLON_").replace("|", "_PIPE_")
                        filters_parts.append(f"{field_escaped}:{type_escaped}:{value_escaped}")
                    if filters_parts:
                        self.settings.setValue("filters", "|".join(filters_parts))
                
                self.settings.endGroup()
            
            self.settings.endGroup()
            self.settings.sync()
        except Exception as e:
            print(f"ERROR saving settings: {e}")
            import traceback
            traceback.print_exc()
    
    def ensure_visibility_field(self, layer):
        """Ensure the visibility field exists in the layer."""
        try:
            field_name = "_fvt_vis"
            field_idx = layer.fields().indexOf(field_name)
            
            if field_idx == -1:
                # Field doesn't exist, create it
                from qgis.core import QgsField
                from qgis.PyQt.QtCore import QVariant
                
                if layer.isEditable():
                    print("WARNING: Layer is in edit mode, cannot add field")
                    return False
                
                layer.startEditing()
                layer.addAttribute(QgsField(field_name, QVariant.Int))
                success = layer.commitChanges()
                
                if success:
                    print(f"Created visibility field '{field_name}' in layer {layer.name()}")
                    # Initialize all features as visible (1)
                    field_idx = layer.fields().indexOf(field_name)
                    if field_idx >= 0:
                        layer.startEditing()
                        for feature in layer.getFeatures():
                            layer.changeAttributeValue(feature.id(), field_idx, 1)
                        layer.commitChanges()
                    return True
                else:
                    print(f"ERROR: Failed to create visibility field")
                    return False
            else:
                return True
        except Exception as e:
            print(f"ERROR ensuring visibility field: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def update_feature_visibility_field(self, layer, feature_id, visible):
        """Update the visibility field for a specific feature."""
        try:
            field_name = "_fvt_vis"
            field_idx = layer.fields().indexOf(field_name)
            
            if field_idx == -1:
                print("WARNING: Visibility field not found")
                return
            
            if layer.isEditable():
                print("WARNING: Layer is in edit mode, cannot update field")
                return
            
            layer.startEditing()
            value = 1 if visible else 0
            layer.changeAttributeValue(feature_id, field_idx, value)
            layer.commitChanges()
        except Exception as e:
            print(f"ERROR updating feature visibility field: {e}")
            import traceback
            traceback.print_exc()
    
    def update_layer_visibility(self, layer):
        """Update layer subset string based on feature visibility states."""
        try:
            # Use the visibility field to filter
            field_name = "_fvt_vis"
            field_idx = layer.fields().indexOf(field_name)
            
            if field_idx == -1:
                # Field doesn't exist, show all
                layer.setSubsetString("")
                return
            
            # Filter to show only features with vis = 1
            layer.setSubsetString(f'"{field_name}" = 1')
            
            # Trigger repaint
            layer.triggerRepaint()
            self.iface.mapCanvas().refresh()
        except Exception as e:
            print(f"ERROR updating layer visibility: {e}")
            import traceback
            traceback.print_exc()
    
    def apply_feature_filter_via_renderer(self, layer, visible_fids):
        """Apply feature visibility filter using renderer."""
        try:
            from qgis.core import QgsRuleBasedRenderer, QgsSymbol, QgsRendererCategory
            from qgis.core import QgsCategorizedSymbolRenderer
            
            # Get all feature IDs
            all_fids = set()
            for feature in layer.getFeatures():
                all_fids.add(feature.id())
            
            visible_set = set(visible_fids)
            hidden_fids = all_fids - visible_set
            
            if not hidden_fids:
                # All visible, no filter needed
                layer.setSubsetString("")
                return
            
            # Create a rule-based renderer that hides specific features
            # We'll use a temporary attribute or use subset string with a workaround
            # Actually, the best approach is to use a virtual field or use renderer opacity
            
            # For now, let's try using a subset string with a workaround:
            # Add a temporary field to track visibility if needed
            # But that's complex. Let's use a simpler approach:
            
            # Use QGIS expression in subset string (QGIS 3.40+ might support this)
            # Actually, let's just use the primary key field approach
            fid_field = self.get_feature_id_field(layer)
            if fid_field:
                fids_str = ",".join(str(fid) for fid in visible_fids)
                subset_string = f'"{fid_field}" IN ({fids_str})'
                layer.setSubsetString(subset_string)
            else:
                # Last resort: create a temporary field
                self.create_temp_visibility_field(layer, visible_fids)
        except Exception as e:
            print(f"ERROR applying renderer filter: {e}")
            import traceback
            traceback.print_exc()
    
    def create_temp_visibility_field(self, layer, visible_fids):
        """Create a temporary field to track visibility."""
        try:
            field_name = "_feature_vis_toggle"
            visible_set = set(visible_fids)
            
            # Check if field exists
            field_idx = layer.fields().indexOf(field_name)
            if field_idx == -1:
                # Add field
                from qgis.core import QgsField
                from qgis.PyQt.QtCore import QVariant
                layer.startEditing()
                layer.addAttribute(QgsField(field_name, QVariant.Int))
                layer.commitChanges()
                field_idx = layer.fields().indexOf(field_name)
            
            # Update field values
            layer.startEditing()
            for feature in layer.getFeatures():
                fid = feature.id()
                if fid in visible_set:
                    layer.changeAttributeValue(feature.id(), field_idx, 1)
                else:
                    layer.changeAttributeValue(feature.id(), field_idx, 0)
            layer.commitChanges()
            
            # Use this field for filtering
            layer.setSubsetString(f'"{field_name}" = 1')
        except Exception as e:
            print(f"ERROR creating temp field: {e}")
            import traceback
            traceback.print_exc()
    
    def get_feature_id_field(self, layer):
        """Get the field name that contains feature IDs."""
        try:
            # Try primary key first
            pk_attrs = layer.primaryKeyAttributes()
            if pk_attrs and len(pk_attrs) > 0:
                field_idx = pk_attrs[0]
                field = layer.fields().field(field_idx)
                return field.name()
            
            # Try common feature ID field names
            common_names = ['fid', 'ogc_fid', 'id', 'gid', 'objectid', 'feature_id']
            for field in layer.fields():
                if field.name().lower() in common_names:
                    return field.name()
            
            # Try first integer field
            for field in layer.fields():
                if field.type() in [2, 4]:  # Integer types
                    return field.name()
            
            return None
        except Exception as e:
            print(f"Warning: Could not determine feature ID field: {e}")
            return None
    
    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        try:
            # Remove visibility fields from all layers
            self.cleanup_visibility_fields()
            
            # Remove dock widget
            if self.dock_widget:
                self.iface.removeDockWidget(self.dock_widget)
                self.dock_widget = None
            
            # Disconnect signals
            try:
                QgsProject.instance().layersAdded.disconnect(self.refresh_layers)
            except:
                pass
            try:
                QgsProject.instance().layersRemoved.disconnect(self.refresh_layers)
            except:
                pass
            
            # Remove toolbar icon and menu item
            if self.action:
                self.iface.removeToolBarIcon(self.action)
                self.iface.removePluginMenu("Show/Hide Each Element Panel", self.action)
                del self.action
        except Exception as e:
            print(f"Warning: Error during unload: {e}")
    
    def cleanup_visibility_fields(self):
        """Remove visibility fields from all layers."""
        try:
            field_name = "_fvt_vis"
            
            # Get all layers
            for layer_id, layer in QgsProject.instance().mapLayers().items():
                if isinstance(layer, QgsVectorLayer):
                    field_idx = layer.fields().indexOf(field_name)
                    if field_idx >= 0:
                        try:
                            # Clear filter first
                            layer.setSubsetString("")
                            
                            # Remove field if layer is not in edit mode
                            if not layer.isEditable():
                                layer.startEditing()
                                layer.deleteAttribute(field_idx)
                                layer.commitChanges()
                                print(f"Removed visibility field from layer {layer.name()}")
                        except Exception as e:
                            print(f"Warning: Could not remove field from {layer.name()}: {e}")
        except Exception as e:
            print(f"ERROR cleaning up visibility fields: {e}")
            import traceback
            traceback.print_exc()

