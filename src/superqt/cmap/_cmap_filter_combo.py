from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cmap import Colormap
from qtpy.QtCore import QSortFilterProxyModel, QStringListModel, Qt, Signal
from qtpy.QtWidgets import (
    QComboBox,
    QCompleter,
    QWidget,
)

from ._cmap_combo import QColormapComboBox
from ._cmap_item_delegate import QColormapItemDelegate
from ._cmap_line_edit import QColormapLineEdit
from ._cmap_utils import try_cast_colormap

if TYPE_CHECKING:
    from cmap._colormap import ColorStopsLike
    from qtpy.QtGui import QKeyEvent


CMAP_ROLE = Qt.ItemDataRole.UserRole + 1


class QColormapFilterComboBox(QColormapComboBox):
    """A drop down menu for selecting colors that allows for text filtering.

    Parameters
    ----------
    parent : QWidget, optional
        The parent widget.
    allow_user_colormaps : bool, optional
        Whether the user can add custom colormaps by clicking the "Add
        Colormap..." item. Default is False. Can also be set with
        `setUserAdditionsAllowed`.
    add_colormap_text: str, optional
        The text to display for the "Add Colormap..." item.
        Default is "Add Colormap...".
    """

    currentColormapChanged = Signal(Colormap)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        allow_user_colormaps: bool = False,
        add_colormap_text: str = "Add Colormap...",
    ) -> None:
        # init QComboBox
        super().__init__(
            parent,
            allow_user_colormaps=allow_user_colormaps,
            add_colormap_text=add_colormap_text,
        )

        # Ensure line edit is editable
        self.setLineEdit(_PopupColormapLineEdit(self))
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setEditable(True)
        self.setDuplicatesEnabled(False)

        # use string list model as source model
        self._source_model = QStringListModel(self)
        # Create a proxy model to handle filtering
        self._proxy_model = QSortFilterProxyModel(self)
        self._proxy_model.setSourceModel(self._source_model)
        self._proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)

        # Setup completer
        self._completer = QCompleter(self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setModel(self._proxy_model)
        self.setCompleter(self._completer)

        # set the delegate for both the popup and the combobox
        delegate = QColormapItemDelegate()
        if popup := self._completer.popup():
            popup.setItemDelegate(delegate)
        self.setItemDelegate(delegate)

        # Update completer model when items change
        self.model().rowsInserted.connect(self._update_completer_model)
        self.model().rowsRemoved.connect(self._update_completer_model)
        self.currentTextChanged.connect(self._on_text_changed)

    def clear(self) -> None:
        super().clear()
        self._update_completer_model()

    def itemColormap(self, index: int) -> Colormap | None:
        """Returns the color of the item at the given index."""
        return self.itemData(index, CMAP_ROLE)

    def addColormap(self, cmap: ColorStopsLike) -> None:
        """Adds the colormap to the QComboBox."""
        super().addColormap(cmap)
        self._update_completer_model()

    def _update_completer_model(self) -> None:
        """Update the completer's model with current items."""
        words = []
        for i in range(self.count()):
            if self.itemText(i) != self._add_color_text:
                words.append(self.itemText(i))

        # Ensure we are updating the source model of the proxy
        if isinstance(self._proxy_model.sourceModel(), QStringListModel):
            source_model = self._proxy_model.sourceModel()
            source_model.setStringList(words)  # Update QStringListModel
            self._proxy_model.invalidate()  # Rebuild proxy mapping

    def _on_text_changed(self, text: str) -> None:
        if (cmap := try_cast_colormap(text)) is not None:
            self.currentColormapChanged.emit(cmap)

    def keyPressEvent(self, e: QKeyEvent | None) -> None:
        if e and e.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            # select the first completion when pressing enter if the popup is visible
            if (completer := self.completer()) and completer.completionCount():
                self.lineEdit().setText(completer.currentCompletion())  # type: ignore
        return super().keyPressEvent(e)


class _PopupColormapLineEdit(QColormapLineEdit):
    def mouseReleaseEvent(self, _: Any) -> None:
        """Show parent popup when clicked.

        Without this, only the down arrow will show the popup.  And if mousePressEvent
        is used instead, the popup will show and then immediately hide.
        Also ensure that the popup is not shown when the user selects text.
        """
        if not self.hasSelectedText():
            parent = self.parent()
            if parent and hasattr(parent, "showPopup"):
                parent.showPopup()
