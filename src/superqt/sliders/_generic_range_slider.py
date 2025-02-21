from collections.abc import Sequence
from typing import Optional, TypeVar, Union

from qtpy import QtGui
from qtpy.QtCore import Property, QEvent, QPoint, QPointF, QRect, QRectF, Qt, Signal
from qtpy.QtWidgets import QSlider, QStyle, QStyleOptionSlider, QStylePainter

from ._generic_slider import CC_SLIDER, SC_GROOVE, SC_HANDLE, SC_NONE, _GenericSlider
from ._range_style import (
    MONTEREY_SLIDER_STYLES_FIX,
    RangeSliderStyle,
    update_styles_from_stylesheet,
)

_T = TypeVar("_T")


SC_BAR = QStyle.SubControl.SC_ScrollBarSubPage


class _GenericRangeSlider(_GenericSlider):
    """MultiHandle Range Slider widget.

    Same API as QSlider, but `value`, `setValue`, `sliderPosition`, and
    `setSliderPosition` are all sequences of integers.

    The `valueChanged` and `sliderMoved` signals also both emit a tuple of
    integers.
    """

    # Emitted when the slider value has changed, with the new slider values
    _valuesChanged = Signal(tuple)

    # Emitted when sliderDown is true and the slider moves
    # This usually happens when the user is dragging the slider
    # The value is the positions of *all* handles.
    _slidersMoved = Signal(tuple)

    def __init__(self, *args, **kwargs):
        self._style = RangeSliderStyle()

        super().__init__(*args, **kwargs)
        self.valueChanged = self._valuesChanged
        self.sliderMoved = self._slidersMoved
        # list of values
        self._value: list[_T] = [20, 80]

        # list of current positions of each handle. same length as _value
        # If tracking is enabled (the default) this will be identical to _value
        self._position: list[_T] = [20, 80]

        # which handle is being pressed/hovered
        self._pressedIndex = 0
        self._hoverIndex = 0

        # whether bar length is constant when dragging the bar
        # if False, the bar can shorten when dragged beyond min/max
        self._bar_is_rigid = True
        # whether clicking on the bar moves all handles, or just the nearest handle
        self._bar_moves_all = True
        self._should_draw_bar = True

        # color

        self.setStyleSheet("")

    # ###############  New Public API  #######################

    def barIsRigid(self) -> bool:
        """Whether bar length is constant when dragging the bar.

        If `False`, the bar can shorten when dragged beyond min/max. Default is `True`.
        """
        return self._bar_is_rigid

    def setBarIsRigid(self, val: bool = True) -> None:
        """Whether bar length is constant when dragging the bar.

        If `False`, the bar can shorten when dragged beyond min/max. Default is `True`.
        """
        self._bar_is_rigid = bool(val)

    def barMovesAllHandles(self) -> bool:
        """Whether clicking on the bar moves all handles, or just the nearest."""
        return self._bar_moves_all

    def setBarMovesAllHandles(self, val: bool = True) -> None:
        """Whether clicking on the bar moves all handles, or just the nearest."""
        self._bar_moves_all = bool(val)

    def barIsVisible(self) -> bool:
        """Whether to show the bar between the first and last handle."""
        return self._should_draw_bar

    def setBarVisible(self, val: bool = True) -> None:
        """Whether to show the bar between the first and last handle."""
        self._should_draw_bar = bool(val)

    def hideBar(self) -> None:
        """Hide the bar between the first and last handle."""
        self.setBarVisible(False)

    def showBar(self) -> None:
        """Show the bar between the first and last handle."""
        self.setBarVisible(True)

    def applyMacStylePatch(self) -> None:
        """Apply a QSS patch to fix sliders on macos>=12 with QT < 6.

        see [FAQ](../faq.md#sliders-not-dragging-properly-on-macos-12) for more details.
        """
        super().applyMacStylePatch()
        self._style._macpatch = True

    # ###############  QtOverrides  #######################

    def value(self) -> tuple[_T, ...]:
        """Get current value of the widget as a tuple of integers."""
        return tuple(self._value)

    def sliderPosition(self):
        """Get current value of the widget as a tuple of integers.

        If tracking is enabled (the default) this will be identical to value().
        """
        return tuple(float(i) for i in self._position)

    def setSliderPosition(  # type: ignore
        self,
        pos: Union[float, Sequence[float]],
        index: Optional[int] = None,
        *,
        reversed: bool = False,
    ) -> None:
        """Set current position of the handles with a sequence of integers.

        Parameters
        ----------
        pos : Union[float, Sequence[float]]
            The new position of the slider handle(s). If a sequence, it must have the
            same length as `value()`. If it is a scalar, index will be used to set the
            position of the handle at that index.
        index : int | None
            The index of the handle to set the position of. If None, the "pressedIndex"
            will be used.
        reversed : bool
            Order in which to set the positions.  Can be useful when setting multiple
            positions, to avoid intermediate overlapping values.
        """
        if isinstance(pos, (list, tuple)):
            val_len = len(self.value())
            if len(pos) != val_len:
                msg = f"'sliderPosition' must have same length as 'value()' ({val_len})"
                raise ValueError(msg)
            pairs = list(enumerate(pos))
        else:
            pairs = [(self._pressedIndex if index is None else index, pos)]

        if reversed:
            pairs = pairs[::-1]

        for idx, position in pairs:
            self._position[idx] = self._bound(position, idx)

        self._doSliderMove()

    def setStyleSheet(self, styleSheet: str) -> None:
        custom_styles = """
        QSlider{
            background-color: none;
        }

        QSlider::add-page:vertical {
            background: none;
            border: none;
        }

        QRangeSlider {
            qproperty-barColor: #9FCBFF;
        }
        """
        return super().setStyleSheet(self._patch_style(styleSheet + custom_styles))

    def _patch_style(self, style: str):
        """Override to patch style options before painting."""
        # sub-page styles render on top of the lower sliders and don't work here.
        if self._style._macpatch and not style:
            style = MONTEREY_SLIDER_STYLES_FIX

        override = f"""
            \n{type(self).__name__}::sub-page:horizontal
                {{background: none; border: none}}
            \n{type(self).__name__}::add-page:vertical
                {{background: none; border: none}}
        """
        return style + override

    def event(self, ev: QEvent) -> bool:
        if ev.type() == QEvent.Type.StyleChange:
            update_styles_from_stylesheet(self)
        return super().event(ev)

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent) -> None:
        if self._pressedControl == SC_BAR:
            ev.accept()
            delta = self._clickOffset - self._pixelPosToRangeValue(
                self._pick(self._event_position(ev))
            )
            self._offsetAllPositions(-delta, self._sldPosAtPress)
        else:
            super().mouseMoveEvent(ev)

    def _event_position(self, event):
        # API changes between PyQt5 (.pos()) and PyQt6 (.position())
        return event.pos() if hasattr(event, "pos") else event.position()

    # ###############  Implementation Details  #######################

    def _setPosition(self, val):
        self._position = list(val)

    def _bound(self, value, index=None):
        if isinstance(value, (list, tuple)):
            return type(value)(self._bound(v) for v in value)
        pos = super()._bound(value)
        if index is not None:
            pos = self._neighbor_bound(pos, index)
        return self._type_cast(pos)

    def _neighbor_bound(self, val, index):
        # make sure we don't go lower than any preceding index:
        min_dist = self.singleStep()
        _lst = self._position
        if index > 0:
            val = max(_lst[index - 1] + min_dist, val)
        # make sure we don't go higher than any following index:
        if index < (len(_lst) - 1):
            val = min(_lst[index + 1] - min_dist, val)
        return val

    def _getBarColor(self):
        return self._style.brush(self._styleOption)

    def _setBarColor(self, color):
        self._style.brush_active = color

    barColor = Property(QtGui.QBrush, _getBarColor, _setBarColor)
    """The color of the bar between the first and last handle."""

    def _offsetAllPositions(self, offset: float, ref=None) -> None:
        if ref is None:
            ref = self._position
        if self._bar_is_rigid:
            # NOTE: This assumes monotonically increasing slider positions
            if offset > 0 and ref[-1] + offset > self.maximum():
                offset = self.maximum() - ref[-1]
            elif ref[0] + offset < self.minimum():
                offset = self.minimum() - ref[0]
        self.setSliderPosition([i + offset for i in ref], reversed=offset > 0)

    def _fixStyleOption(self, option):
        pass

    @property
    def _optSliderPositions(self):
        return [self._to_qinteger_space(p - self._minimum) for p in self._position]

    # SubControl Positions

    def _handleRect(
        self, handle_index: int, opt: Optional[QStyleOptionSlider] = None
    ) -> QRect:
        """Return the QRect for all handles."""
        opt = opt or self._styleOption
        opt.sliderPosition = self._optSliderPositions[handle_index]
        return self.style().subControlRect(CC_SLIDER, opt, SC_HANDLE, self)

    def _barRect(self, opt: QStyleOptionSlider) -> QRect:
        """Return the QRect for the bar between the outer handles."""
        r_groove = self.style().subControlRect(CC_SLIDER, opt, SC_GROOVE, self)
        r_bar = QRectF(r_groove)
        hdl_low, hdl_high = self._handleRect(0, opt), self._handleRect(-1, opt)

        thickness = self._style.thickness(opt)
        offset = self._style.offset(opt)

        if opt.orientation == Qt.Orientation.Horizontal:
            r_bar.setTop(r_bar.center().y() - thickness / 2 + offset)
            r_bar.setHeight(thickness)
            r_bar.setLeft(hdl_low.center().x())
            r_bar.setRight(hdl_high.center().x())
        else:
            r_bar.setLeft(r_bar.center().x() - thickness / 2 + offset)
            r_bar.setWidth(thickness)
            r_bar.setBottom(hdl_low.center().y())
            r_bar.setTop(hdl_high.center().y())

        return r_bar

    # Painting

    def _drawBar(self, painter: QStylePainter, opt: QStyleOptionSlider):
        brush = self._style.brush(opt)
        r_bar = self._barRect(opt)
        if isinstance(brush, QtGui.QGradient):
            brush.setStart(r_bar.topLeft())
            brush.setFinalStop(r_bar.bottomRight())
        painter.setPen(self._style.pen(opt))
        painter.setBrush(brush)
        painter.drawRect(r_bar)

    def _draw_handle(self, painter: QStylePainter, opt: QStyleOptionSlider):
        if self._should_draw_bar:
            self._drawBar(painter, opt)

        opt.subControls = SC_HANDLE
        pidx = self._pressedIndex if self._pressedControl == SC_HANDLE else -1
        hidx = self._hoverIndex if self._hoverControl == SC_HANDLE else -1
        for idx, pos in enumerate(self._optSliderPositions):
            opt.sliderPosition = pos
            # make pressed handles appear sunken
            if idx == pidx:
                opt.state |= QStyle.StateFlag.State_Sunken
            else:
                opt.state = opt.state & ~QStyle.StateFlag.State_Sunken
            opt.activeSubControls = SC_HANDLE if idx == hidx else SC_NONE
            painter.drawComplexControl(CC_SLIDER, opt)

    def _updateHoverControl(self, pos):
        old_hover = self._hoverControl, self._hoverIndex
        self._hoverControl, self._hoverIndex = self._getControlAtPos(pos)
        if (self._hoverControl, self._hoverIndex) != old_hover:
            self.update()

    def _updatePressedControl(self, pos):
        opt = self._styleOption
        self._pressedControl, self._pressedIndex = self._getControlAtPos(pos, opt)

    def _setClickOffset(self, pos):
        if self._pressedControl == SC_BAR:
            self._clickOffset = self._pixelPosToRangeValue(self._pick(pos))
            self._sldPosAtPress = tuple(self._position)
        elif self._pressedControl == SC_HANDLE:
            hr = self._handleRect(self._pressedIndex)
            self._clickOffset = self._pick(pos - hr.topLeft())

    # NOTE: this is very much tied to mousepress... not a generic "get control"
    def _getControlAtPos(
        self, pos: QPoint, opt: Optional[QStyleOptionSlider] = None
    ) -> tuple[QStyle.SubControl, int]:
        """Update self._pressedControl based on ev.pos()."""
        opt = opt or self._styleOption

        if isinstance(pos, QPointF):
            pos = pos.toPoint()

        for i in range(len(self._position)):
            if self._handleRect(i, opt).contains(pos):
                return (SC_HANDLE, i)

        click_pos = self._pixelPosToRangeValue(self._pick(pos))
        for i, p in enumerate(self._position):
            if p > click_pos:
                if i > 0:
                    # the click was in an internal segment
                    if self._bar_moves_all:
                        return (SC_BAR, i)
                    avg = (self._position[i - 1] + self._position[i]) / 2
                    return (SC_HANDLE, i - 1 if click_pos < avg else i)
                # the click was below the minimum slider
                return (SC_HANDLE, 0)
        # the click was above the maximum slider
        return (SC_HANDLE, len(self._position) - 1)

    def _execute_scroll(self, steps_to_scroll, modifiers):
        if modifiers & Qt.KeyboardModifier.AltModifier:
            self._spreadAllPositions(shrink=steps_to_scroll < 0)
        else:
            self._offsetAllPositions(steps_to_scroll)
        self.triggerAction(QSlider.SliderAction.SliderMove)

    def _has_scroll_space_left(self, offset):
        return (offset > 0 and max(self._value) < self._maximum) or (
            offset < 0 and min(self._value) < self._minimum
        )

    def _spreadAllPositions(self, shrink=False, gain=1.1, ref=None) -> None:
        if ref is None:
            ref = self._position
        # if self._bar_is_rigid:  # TODO

        if shrink:
            gain = 1 / gain
        center = abs(ref[-1] + ref[0]) / 2
        self.setSliderPosition([((i - center) * gain) + center for i in ref])
