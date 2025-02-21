import platform
from unittest.mock import patch

import numpy as np
import pytest
from qtpy import API_NAME

try:
    from cmap import Colormap
except ImportError:
    pytest.skip("cmap not installed", allow_module_level=True)

from qtpy.QtCore import QRect
from qtpy.QtGui import QPainter, QPixmap
from qtpy.QtWidgets import QStyleOptionViewItem, QWidget

from superqt import QColormapComboBox, QColormapFilterComboBox
from superqt.cmap import (
    CmapCatalogComboBox,
    QColormapItemDelegate,
    QColormapLineEdit,
    _cmap_combo,
    draw_colormap,
)
from superqt.utils import qimage_to_array


def test_draw_cmap(qtbot):
    # draw into a QWidget
    wdg = QWidget()
    qtbot.addWidget(wdg)
    draw_colormap(wdg, "viridis")
    # draw into any QPaintDevice
    draw_colormap(QPixmap(), "viridis")
    # pass a painter an explicit colormap and a rect
    draw_colormap(QPainter(), Colormap(("red", "yellow", "blue")), QRect())
    # test with a border
    draw_colormap(wdg, "viridis", border_color="red", border_width=2)

    with pytest.raises(TypeError, match="Expected a QPainter or QPaintDevice instance"):
        draw_colormap(QRect(), "viridis")  # type: ignore

    with pytest.raises(TypeError, match="Expected a Colormap instance or something"):
        draw_colormap(QPainter(), "not a recognized string or cmap", QRect())


def test_cmap_draw_result():
    """Test that the image drawn actually looks correct."""
    # draw into any QPaintDevice
    w = 100
    h = 20
    pix = QPixmap(w, h)
    cmap = Colormap("viridis")
    draw_colormap(pix, cmap)

    ary1 = cmap(np.tile(np.linspace(0, 1, w), (h, 1)), bytes=True)
    ary2 = qimage_to_array(pix.toImage())

    # there are some subtle differences between how qimage draws and how
    # cmap draws, so we can't assert that the arrays are exactly equal.
    # they are visually indistinguishable, and numbers are close within 4 (/255) values
    # and linux, for some reason, is a bit more different``
    atol = 8 if platform.system() == "Linux" else 4
    np.testing.assert_allclose(ary1, ary2, atol=atol)

    cmap2 = Colormap(("#230777",), name="MyMap")
    draw_colormap(pix, cmap2)  # include transparency


def test_catalog_combo(qtbot):
    wdg = CmapCatalogComboBox()
    qtbot.addWidget(wdg)
    wdg.show()

    wdg.setCurrentText("viridis")
    assert wdg.currentColormap() == Colormap("viridis")


@pytest.mark.parametrize("widget_class", [QColormapComboBox, QColormapFilterComboBox])
def test_cmap_filter_combo(qtbot, widget_class):
    wdg = widget_class(allow_user_colormaps=True)
    qtbot.addWidget(wdg)
    wdg.show()
    assert wdg.userAdditionsAllowed()

    with qtbot.waitSignal(wdg.currentColormapChanged):
        wdg.addColormaps([Colormap("viridis"), "magma", ("red", "blue", "green")])
    assert wdg.currentColormap().name.split(":")[-1] == "viridis"

    with pytest.raises(ValueError, match="Invalid colormap"):
        wdg.addColormap("not a recognized string or cmap")

    assert wdg.currentColormap().name.split(":")[-1] == "viridis"
    assert wdg.currentIndex() == 0
    assert wdg.count() == 4  # includes "Add Colormap..."
    wdg.setCurrentColormap("magma")
    assert wdg.count() == 4  # make sure we didn't duplicate
    assert wdg.currentIndex() == 1

    if API_NAME == "PySide2":
        return  # the rest fails on CI... but works locally

    # click the Add Colormap... item
    with qtbot.waitSignal(wdg.currentColormapChanged):
        with patch.object(_cmap_combo._CmapNameDialog, "exec", return_value=True):
            wdg._on_activated(wdg.count() - 1)

    assert wdg.count() == 5
    # this could potentially fail in the future if cmap catalog changes
    # but mocking the return value of the dialog is also annoying
    assert wdg.itemColormap(3).name.split(":")[-1] == "accent"

    # click the Add Colormap... item, but cancel the dialog
    with patch.object(_cmap_combo._CmapNameDialog, "exec", return_value=False):
        wdg._on_activated(wdg.count() - 1)


def test_cmap_item_delegate(qtbot):
    wdg = CmapCatalogComboBox()
    qtbot.addWidget(wdg)
    view = wdg.view()
    delegate = view.itemDelegate()
    assert isinstance(delegate, QColormapItemDelegate)

    # smoke tests:
    painter = QPainter()
    option = QStyleOptionViewItem()
    index = wdg.model().index(0, 0)
    delegate._colormap_fraction = 1
    delegate.paint(painter, option, index)
    delegate._colormap_fraction = 0.33
    delegate.paint(painter, option, index)

    assert delegate.sizeHint(option, index) == delegate._item_size


def test_cmap_line_edit(qtbot, qapp):
    wdg = QColormapLineEdit()
    qtbot.addWidget(wdg)
    wdg.show()

    wdg.setColormap("viridis")
    assert wdg.colormap() == Colormap("viridis")
    wdg.setText("magma")  # also works if the name is recognized
    assert wdg.colormap() == Colormap("magma")
    qapp.processEvents()
    qtbot.wait(10)  # force the paintEvent

    wdg.setFractionalColormapWidth(1)
    assert wdg.fractionalColormapWidth() == 1
    wdg.update()
    qapp.processEvents()
    qtbot.wait(10)  # force the paintEvent

    wdg.setText("not-a-cmap")
    assert wdg.colormap() is None
    # or

    wdg.setFractionalColormapWidth(0.3)
    wdg.setColormap(None)
    assert wdg.colormap() is None
    qapp.processEvents()
    qtbot.wait(10)  # force the paintEvent
