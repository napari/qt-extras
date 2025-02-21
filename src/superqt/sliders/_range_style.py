from __future__ import annotations

import platform
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtGui import (
    QBrush,
    QColor,
    QGradient,
    QLinearGradient,
    QPalette,
    QRadialGradient,
)
from qtpy.QtWidgets import QApplication, QSlider, QStyleOptionSlider

if TYPE_CHECKING:
    from ._generic_range_slider import _GenericRangeSlider


@dataclass
class RangeSliderStyle:
    brush_active: str | None = None
    brush_inactive: str | None = None
    brush_disabled: str | None = None
    pen_active: str | None = None
    pen_inactive: str | None = None
    pen_disabled: str | None = None
    vertical_thickness: float | None = None
    horizontal_thickness: float | None = None
    tick_offset: float | None = None
    tick_bar_alpha: float | None = None
    v_offset: float | None = None
    h_offset: float | None = None
    has_stylesheet: bool = False
    _macpatch: bool = False

    def brush(self, opt: QStyleOptionSlider) -> QBrush:
        cg = opt.palette.currentColorGroup()
        attr = {
            QPalette.ColorGroup.Active: "brush_active",  # 0
            QPalette.ColorGroup.Disabled: "brush_disabled",  # 1
            QPalette.ColorGroup.Inactive: "brush_inactive",  # 2
        }[cg]
        _val = getattr(self, attr)
        if not _val:
            if self.has_stylesheet:
                # if someone set a general style sheet but didn't specify
                # :active, :inactive, etc... then Qt just uses whatever they
                # DID specify
                for i in ("active", "inactive", "disabled"):
                    _val = getattr(self, f"brush_{i}")
                    if _val:
                        break
            else:
                _val = getattr(SYSTEM_STYLE, attr)

        if _val is None:
            return QBrush()

        if isinstance(_val, str):
            val = QColor(_val)
            if not val.isValid():
                val = parse_color(_val, default_attr=attr)
        else:
            val = _val

        if opt.tickPosition != QSlider.TickPosition.NoTicks:
            if isinstance(val, QColor):
                val.setAlphaF(self.tick_bar_alpha or SYSTEM_STYLE.tick_bar_alpha)
            elif isinstance(val, QGradient):
                for i in range(val.colorCount()):
                    color = val.colorAt(i)
                    color.setAlphaF(self.tick_bar_alpha or SYSTEM_STYLE.tick_bar_alpha)
                    val.setColorAt(i, color)

        return QBrush(val)

    def pen(self, opt: QStyleOptionSlider) -> Qt.PenStyle | QColor:
        cg = opt.palette.currentColorGroup()
        attr = {
            QPalette.ColorGroup.Active: "pen_active",  # 0
            QPalette.ColorGroup.Disabled: "pen_disabled",  # 1
            QPalette.ColorGroup.Inactive: "pen_inactive",  # 2
        }[cg]
        val = getattr(self, attr) or getattr(SYSTEM_STYLE, attr)
        if not val:
            return Qt.PenStyle.NoPen
        if isinstance(val, str):
            val = QColor(val)
        if opt.tickPosition != QSlider.TickPosition.NoTicks:
            val.setAlphaF(self.tick_bar_alpha or SYSTEM_STYLE.tick_bar_alpha)
        return val

    def offset(self, opt: QStyleOptionSlider) -> int:
        off = 0
        if not self.has_stylesheet:
            tp = opt.tickPosition
            if opt.orientation == Qt.Orientation.Horizontal:
                if not self._macpatch:
                    off += self.h_offset or SYSTEM_STYLE.h_offset or 0
            else:
                off += self.v_offset or SYSTEM_STYLE.v_offset or 0
            if tp == QSlider.TickPosition.TicksAbove:
                off += self.tick_offset or SYSTEM_STYLE.tick_offset
            elif tp == QSlider.TickPosition.TicksBelow:
                off -= self.tick_offset or SYSTEM_STYLE.tick_offset
        return off

    def thickness(self, opt: QStyleOptionSlider) -> float:
        if opt.orientation == Qt.Orientation.Horizontal:
            return self.horizontal_thickness or SYSTEM_STYLE.horizontal_thickness
        else:
            return self.vertical_thickness or SYSTEM_STYLE.vertical_thickness


# ##########  System-specific default styles ############

BASE_STYLE = RangeSliderStyle(
    brush_active="#3B88FD",
    brush_inactive="#8F8F8F",
    brush_disabled="#BBBBBB",
    pen_active=None,
    pen_inactive=None,
    pen_disabled=None,
    vertical_thickness=4,
    horizontal_thickness=4,
    tick_offset=0,
    tick_bar_alpha=0.3,
    v_offset=0,
    h_offset=0,
    has_stylesheet=False,
)

CATALINA_STYLE = replace(
    BASE_STYLE,
    brush_active="#3B88FD",
    brush_inactive="#8F8F8F",
    brush_disabled="#D2D2D2",
    horizontal_thickness=3,
    vertical_thickness=3,
    tick_bar_alpha=0.3,
    tick_offset=4,
)

# I can no longer reproduce the cases in which this was necessary
# if QT_VERSION and int(QT_VERSION.split(".")[0]) == 6:
#     CATALINA_STYLE = replace(CATALINA_STYLE, tick_offset=2)

BIG_SUR_STYLE = replace(
    CATALINA_STYLE,
    brush_active="#0A81FE",
    brush_inactive="#D5D5D5",
    brush_disabled="#E6E6E6",
    tick_offset=0,
    horizontal_thickness=4,
    vertical_thickness=4,
    h_offset=-2,
    tick_bar_alpha=0.2,
)

# I can no longer reproduce the cases in which this was necessary
# if QT_VERSION and int(QT_VERSION.split(".")[0]) == 6:
#     BIG_SUR_STYLE = replace(BIG_SUR_STYLE, tick_offset=-3)

WINDOWS_STYLE = replace(
    BASE_STYLE,
    brush_active="#550179D7",
    brush_inactive="#330179D7",
    brush_disabled=None,
)

LINUX_STYLE = replace(
    BASE_STYLE,
    brush_active="#44A0D9",
    brush_inactive="#44A0D9",
    brush_disabled="#44A0D9",
    pen_active="#286384",
    pen_inactive="#286384",
    pen_disabled="#286384",
)

SYSTEM = platform.system()
if SYSTEM == "Darwin":
    if int(platform.mac_ver()[0].split(".", maxsplit=1)[0]) >= 11:
        SYSTEM_STYLE = BIG_SUR_STYLE
    else:
        SYSTEM_STYLE = CATALINA_STYLE
elif SYSTEM == "Windows":
    SYSTEM_STYLE = WINDOWS_STYLE
elif SYSTEM == "Linux":
    SYSTEM_STYLE = LINUX_STYLE
else:
    SYSTEM_STYLE = BASE_STYLE


# ################ Stylesheet parsing logic ########################

qlineargrad_pattern = re.compile(
    r"""
    qlineargradient\(
        x1:\s*(?P<x1>\d*\.?\d+),\s*
        y1:\s*(?P<y1>\d*\.?\d+),\s*
        x2:\s*(?P<x2>\d*\.?\d+),\s*
        y2:\s*(?P<y2>\d*\.?\d+),\s*
        stop:0\s*(?P<stop0>\S+),.*
        stop:1\s*(?P<stop1>\S+)
    \)""",
    re.X,
)

qradial_pattern = re.compile(
    r"""
    qradialgradient\(
        cx:\s*(?P<cx>\d*\.?\d+),\s*
        cy:\s*(?P<cy>\d*\.?\d+),\s*
        radius:\s*(?P<radius>\d*\.?\d+),\s*
        fx:\s*(?P<fx>\d*\.?\d+),\s*
        fy:\s*(?P<fy>\d*\.?\d+),\s*
        stop:0\s*(?P<stop0>\S+),.*
        stop:1\s*(?P<stop1>\S+)
    \)""",
    re.X,
)

rgba_pattern = re.compile(
    r"""
    rgba?\(
        (?P<r>\d+),\s*
        (?P<g>\d+),\s*
        (?P<b>\d+),?\s*(?P<a>\d+)?\)
    """,
    re.X,
)


def parse_color(color: str, default_attr: str) -> QColor | QGradient:
    qc = QColor(color)
    if qc.isValid():
        return qc

    match = rgba_pattern.search(color)
    if match:
        rgba = [int(x) if x else 255 for x in match.groups()]
        return QColor(*rgba)

    # try linear gradient:
    match = qlineargrad_pattern.search(color)
    grad: QGradient
    if match:
        grad = QLinearGradient(*(float(i) for i in match.groups()[:4]))
        grad.setColorAt(0, QColor(match.groupdict()["stop0"]))
        grad.setColorAt(1, QColor(match.groupdict()["stop1"]))
        return grad

    # try linear gradient:
    match = qradial_pattern.search(color)
    if match:
        grad = QRadialGradient(*(float(i) for i in match.groups()[:5]))
        grad.setColorAt(0, QColor(match.groupdict()["stop0"]))
        grad.setColorAt(1, QColor(match.groupdict()["stop1"]))
        return grad

    # fallback to dark gray
    return QColor(getattr(SYSTEM_STYLE, default_attr))


def update_styles_from_stylesheet(obj: _GenericRangeSlider) -> None:
    qss: str = obj.styleSheet()

    parent = obj.parent()
    while parent and hasattr(parent, "styleSheet"):
        qss = parent.styleSheet() + qss
        parent = parent.parent()
    qss = QApplication.instance().styleSheet() + qss
    if not qss:
        return
    if MONTEREY_SLIDER_STYLES_FIX in qss:
        qss = qss.replace(MONTEREY_SLIDER_STYLES_FIX, "")
        obj._style._macpatch = True
    else:
        obj._style._macpatch = False

    # Find bar height/width
    for orient, dim in (("horizontal", "height"), ("vertical", "width")):
        match = re.search(rf"Slider::groove:{orient}\s*{{\s*([^}}]+)}}", qss, re.S)
        if match:
            for line in reversed(match.groups()[0].splitlines()):
                bgrd = re.search(rf"{dim}\s*:\s*(\d+)", line)
                if bgrd:
                    thickness = float(bgrd.groups()[-1])
                    setattr(obj._style, f"{orient}_thickness", thickness)
                    obj._style.has_stylesheet = True

    # Find bar color
    match = re.search(r"QRangeSlider\s*{\s*([^}]+)}", qss, re.S)
    if match:
        for line in reversed(match.groups()[0].splitlines()):
            bgrd = re.search(r"qproperty-barColor\s*:\s*(.+);", line)
            if bgrd:
                obj._setBarColor(bgrd.groups()[-1])
                obj._style.has_stylesheet = True


# a fix for https://bugreports.qt.io/browse/QTBUG-98093

MONTEREY_SLIDER_STYLES_FIX = """
/* MONTEREY_SLIDER_STYLES_FIX */

QSlider::groove {
    background: #DFDFDF;
    border: 1px solid #DBDBDB;
    border-radius: 2px;
}
QSlider::groove:horizontal {
    height: 2px;
    margin: 2px;
}
QSlider::groove:vertical {
    width: 2px;
    margin: 2px 0 6px 0;
}


QSlider::handle {
    background: white;
    border: 0.5px solid #DADADA;
    width: 19.5px;
    height: 19.5px;
    border-radius: 10.5px;
}
QSlider::handle:horizontal {
    margin: -10px -2px;
}
QSlider::handle:vertical {
    margin: -2px -10px;
}

QSlider::handle:pressed {
    background: #F0F0F0;
}

QSlider::sub-page:horizontal {
    background: #0981FE;
    border-radius: 2px;
    margin: 2px;
    height: 2px;
}
QSlider::add-page:vertical {
    background: #0981FE;
    border-radius: 2px;
    margin: 2px 0 6px 0;
    width: 2px;
}
""".strip()
