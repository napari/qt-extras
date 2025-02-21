from qtpy.QtWidgets import QApplication, QVBoxLayout, QWidget

from superqt.cmap import CmapCatalogComboBox, QColormapComboBox, QColormapFilterComboBox

app = QApplication([])

wdg = QWidget()
layout = QVBoxLayout(wdg)

catalog_combo = CmapCatalogComboBox(interpolation="linear")

selected_cmaps = ["viridis", "plasma", "magma", "inferno", "turbo"]

selected_cmap_combo = QColormapComboBox(allow_user_colormaps=True)
selected_cmap_combo.addColormaps(selected_cmaps)

filter_cmap_combo = QColormapFilterComboBox(allow_user_colormaps=True)
filter_cmap_combo.addColormaps(selected_cmaps)

layout.addWidget(catalog_combo)
layout.addWidget(selected_cmap_combo)
layout.addWidget(filter_cmap_combo)

wdg.show()
app.exec()
