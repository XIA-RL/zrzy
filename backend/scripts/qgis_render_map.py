#!/usr/bin/env python3
"""
PyQGIS 无头制图脚本 —— 智能体流程正式地图的唯一渲染引擎。

必须用 python-qgis-ltr.bat 调用：
    python-qgis-ltr.bat qgis_render_map.py --input x.tif --output x.png --mode lulc --title "标题"

mode: lulc | habitat | carbon | auto

版式规范（所有 mode 共用，仅图例与配色不同）：
  - A4 横版、双线图框
  - 地图 CRS = EPSG:4326，10′ 经纬网，标注写在双线间隙
  - 右上指北针、右下 Miles 比例尺
  - 左下图例（LULC 分类色块；连续值高/低色块）
  - 导出 200 DPI PNG

业务入口请用 plot_standard_map.py / invoke_qgis_map.py，勿直接复制本文件逻辑。
"""
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (
    QgsApplication, QgsColorRampShader, QgsCoordinateReferenceSystem,
    QgsPalettedRasterRenderer, QgsProject, QgsRasterLayer, QgsRasterShader,
    QgsSingleBandPseudoColorRenderer, QgsTextFormat,
    QgsLayoutExporter, QgsLayoutItemLabel, QgsLayoutItemLegend,
    QgsLayoutItemMap, QgsLayoutItemPage, QgsLayoutItemPicture,
    QgsLayoutItemScaleBar, QgsLayoutItemShape,
    QgsLayoutMeasurement, QgsLayoutPoint, QgsLayoutSize, QgsPrintLayout,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPen

try:
    from qgis.core import QgsUnitTypes
    _KM = QgsUnitTypes.DistanceKilometers
    _MI = QgsUnitTypes.DistanceMiles
    _MM = QgsUnitTypes.LayoutMillimeters
except Exception:
    try:
        from qgis.core import Qgis
        _KM = Qgis.DistanceUnit.Kilometers
        _MI = Qgis.DistanceUnit.Miles
        _MM = Qgis.LayoutUnit.Millimeters
    except Exception:
        _KM = 1; _MI = 2; _MM = 0

try:
    from qgis.core import QgsLegendStyle
except ImportError:
    QgsLegendStyle = None

# ── 颜色 ──────────────────────────────────────────────────────────────────────

LULC_CLASSES = {
    1: ("耕地",    "#C4A574"),
    2: ("林地",    "#2E8B2E"),
    3: ("草地",    "#90EE90"),
    4: ("水域",    "#1E6FD9"),
    5: ("居民用地", "#E02020"),
}
RDYLGN = [(0.0,"#d73027"),(0.25,"#fc8d59"),(0.5,"#ffffbf"),(0.75,"#91cf60"),(1.0,"#1a9850")]
YLGN   = [(0.0,"#ffffe5"),(0.25,"#c2e699"),(0.5,"#78c679"),(0.75,"#31a354"),(1.0,"#006837")]
VIRIDIS= [(0.0,"#440154"),(0.25,"#31688e"),(0.5,"#35b779"),(0.75,"#90d743"),(1.0,"#fde725")]
# 碳储量参考图：低值黄、高值红
CARBON_REF = [(0.0, "#ffff00"), (0.35, "#fd8d3c"), (0.7, "#f03b20"), (1.0, "#bd0026")]

# ── 辅助 ──────────────────────────────────────────────────────────────────────

def _mm(v):    return QgsLayoutMeasurement(v, _MM)
def _pt(x, y): return QgsLayoutPoint(x, y, _MM)
def _sz(w, h): return QgsLayoutSize(w, h, _MM)

def _text_fmt(family, size, bold=False):
    fmt = QgsTextFormat()
    f = QFont(family, int(size))
    f.setBold(bold)
    fmt.setFont(f)
    fmt.setSize(size)
    return fmt

def _font(family, size, bold=False):
    f = QFont(family, int(size))
    f.setBold(bold)
    return f

def _load_chinese_fonts():
    from qgis.PyQt.QtGui import QFontDatabase
    win_fonts = Path(r"C:\Windows\Fonts")
    for fname in ["msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc"]:
        fp = win_fonts / fname
        if fp.is_file():
            QFontDatabase.addApplicationFont(str(fp))

# ── 渲染器 ────────────────────────────────────────────────────────────────────

def _lulc_renderer(layer):
    classes = [QgsPalettedRasterRenderer.Class(v, QColor(c), lbl)
               for v, (lbl, c) in LULC_CLASSES.items()]
    return QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes)

def _continuous_renderer(layer, stops, vmin, vmax):
    sf = QgsColorRampShader(vmin, vmax)
    sf.setColorRampType(QgsColorRampShader.Interpolated)
    sf.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(vmin + r*(vmax-vmin), QColor(c))
        for r, c in stops
    ])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(sf)
    rend = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    rend.setClassificationMin(vmin)
    rend.setClassificationMax(vmax)
    return rend

# ── SVG 指北针 ────────────────────────────────────────────────────────────────

def _qgis_install_roots() -> list[Path]:
    """优先从环境变量 QGIS_PYTHON_BAT（.env）推导安装根目录。"""
    roots: list[Path] = []
    bat = os.environ.get("QGIS_PYTHON_BAT", "").strip()
    if bat:
        bat_path = Path(bat).resolve()
        # .../QGIS/bin/python-qgis-ltr.bat → QGIS 安装根
        if bat_path.parent.name.lower() == "bin":
            roots.append(bat_path.parent.parent)
        roots.append(bat_path.parent)
    for candidate in (
        Path(r"C:\Program Files\QGIS 3.34"),
        Path(r"C:\Program Files\QGIS 3.38"),
        Path(r"C:\Program Files\QGIS 3.40"),
    ):
        if candidate not in roots:
            roots.append(candidate)
    return roots


def _north_svg(compass=False):
    names = ["NorthArrow_02.svg", "NorthArrow_10.svg", "NorthArrow_04.svg", "NorthArrow_01.svg"] if compass else ["NorthArrow_04.svg", "NorthArrow_01.svg"]
    for base in _qgis_install_roots():
        if not base.is_dir():
            continue
        for name in names:
            hits = list(base.glob(f"**/{name}"))
            if hits:
                return str(hits[0])
    return None

# ── 比例尺档位 ────────────────────────────────────────────────────────────────

def _map_width_miles(layer):
    try:
        from qgis.core import QgsDistanceArea, QgsPointXY
        da = QgsDistanceArea()
        da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
        da.setEllipsoid("WGS84")
        ext = layer.extent()
        km = da.measureLine(
            QgsPointXY(ext.xMinimum(), (ext.yMinimum()+ext.yMaximum())/2),
            QgsPointXY(ext.xMaximum(), (ext.yMinimum()+ext.yMaximum())/2),
        ) / 1000
        return km * 0.621371
    except Exception:
        return 30.0

def _percentile_bounds(layer, low=2.0, high=98.0):
    """按百分位拉伸，避免整图偏红。"""
    try:
        import numpy as np
        from osgeo import gdal
        ds = gdal.Open(layer.source())
        band = ds.GetRasterBand(1)
        arr = band.ReadAsArray().astype("float64")
        nodata = band.GetNoDataValue()
        mask = np.isfinite(arr)
        if nodata is not None:
            mask &= arr != nodata
        vals = arr[mask]
        if vals.size == 0:
            raise ValueError("empty raster")
        return float(np.percentile(vals, low)), float(np.percentile(vals, high))
    except Exception:
        stats = layer.dataProvider().bandStatistics(1)
        return stats.minimumValue, stats.maximumValue

def _scalebar_miles(layer):
    """4 段比例尺，每段英里数（参考图约 22 英里总长）。"""
    width_mi = _map_width_miles(layer)
    target_total = width_mi * 0.58
    nice_totals = [11, 16.5, 22, 27.5, 33]
    total = min(nice_totals, key=lambda x: abs(x - target_total))
    return total / 4.0, total
def _scalebar_km(layer):
    """返回比例尺每段公里数（4 段，总长约占图宽 28%）。"""
    try:
        from qgis.core import QgsDistanceArea, QgsPointXY
        da = QgsDistanceArea()
        da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
        da.setEllipsoid("WGS84")
        ext = layer.extent()
        w = da.measureLine(
            QgsPointXY(ext.xMinimum(), (ext.yMinimum()+ext.yMaximum())/2),
            QgsPointXY(ext.xMaximum(), (ext.yMinimum()+ext.yMaximum())/2),
        ) / 1000
    except Exception:
        w = 50.0
    target_total = w * 0.28
    nice_totals = [2, 5, 10, 20, 25, 40, 50, 80, 100]
    total = min(nice_totals, key=lambda x: abs(x - target_total))
    return total / 4.0

def _nice_bounds(vmin, vmax):
    if vmax >= 1000:
        return round(vmin), round(vmax)
    if vmax >= 100:
        return round(vmin, 1), round(vmax, 1)
    return round(vmin, 2), round(vmax, 2)

LAYER_LABELS = {
    "carbon":  "碳储量 (MgC/pixel)",
    "habitat": "生境质量指数",
    "lulc":    "土地利用类型",
    "auto":    "分析结果",
}

def _make_colorbar_image(stops, vmin, vmax, path: Path, height=200, width=24):
    img = QImage(width, height, QImage.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    painter = QPainter(img)
    grad = QLinearGradient(0, height, 0, 0)
    for ratio, color in stops:
        grad.setColorAt(ratio, QColor(color))
    painter.fillRect(1, 1, width - 2, height - 2, grad)
    painter.setPen(QPen(QColor(0, 0, 0), 1))
    painter.drawRect(0, 0, width - 1, height - 1)
    painter.end()
    img.save(str(path))

def _add_label(layout, text, x, y, w, h, size=7, bold=False, halign=Qt.AlignLeft, rotation=0):
    lb = QgsLayoutItemLabel(layout)
    lb.setText(text)
    lb.setTextFormat(_text_fmt("Microsoft YaHei", size, bold=bold))
    lb.setHAlign(halign)
    lb.setVAlign(Qt.AlignVCenter)
    if rotation:
        try:
            # 以中心为锚点旋转，便于对准格网线
            from qgis.core import QgsLayoutItem
            lb.setReferencePoint(QgsLayoutItem.Middle)
        except Exception:
            pass
        lb.attemptResize(_sz(w, h))
        lb.attemptMove(_pt(x, y))
        try:
            lb.setItemRotation(rotation)
        except Exception:
            pass
    else:
        lb.attemptMove(_pt(x, y))
        lb.attemptResize(_sz(w, h))
    layout.addLayoutItem(lb)
    return lb

def _add_continuous_legend(layout, label, stops, vmin, vmax, x, y, w, h):
    frame = QgsLayoutItemShape(layout)
    frame.setShapeType(QgsLayoutItemShape.Rectangle)
    frame.attemptMove(_pt(x, y))
    frame.attemptResize(_sz(w, h))
    frame.setFrameEnabled(True)
    frame.setFrameStrokeWidth(_mm(0.4))
    frame.setBackgroundEnabled(True)
    layout.addLayoutItem(frame)

    _add_label(layout, "图例", x + 2, y + 2, w - 4, 6, size=8, bold=True, halign=Qt.AlignHCenter)
    _add_label(layout, label, x + 2, y + 8, w - 4, 6, size=7, halign=Qt.AlignHCenter)

    bar_x = x + (w - 10) / 2
    bar_y = y + 16
    bar_h = h - 28
    bar_png = Path(tempfile.gettempdir()) / "qgis_colorbar.png"
    _make_colorbar_image(stops, vmin, vmax, bar_png, height=200, width=24)

    bar = QgsLayoutItemPicture(layout)
    bar.setPicturePath(str(bar_png))
    bar.attemptMove(_pt(bar_x, bar_y))
    bar.attemptResize(_sz(10, bar_h))
    layout.addLayoutItem(bar)

    _add_label(layout, str(vmax), bar_x + 11, bar_y, w - bar_x - 11 + x, 5, size=7)
    _add_label(layout, str(vmin), bar_x + 11, bar_y + bar_h - 4, w - bar_x - 11 + x, 5, size=7)

def _add_color_patch(layout, color, x, y, size=5):
    patch = QgsLayoutItemShape(layout)
    patch.setShapeType(QgsLayoutItemShape.Rectangle)
    patch.attemptMove(_pt(x, y))
    patch.attemptResize(_sz(size, size))
    try:
        from qgis.core import QgsFillSymbol
        sym = QgsFillSymbol.createSimple({
            "color": color,
            "outline_color": "0,0,0,255",
            "outline_width": "0.25",
        })
        patch.setSymbol(sym)
    except Exception:
        patch.setBackgroundEnabled(True)
        patch.setBackgroundColor(QColor(color))
        patch.setFrameEnabled(True)
        patch.setFrameStrokeWidth(_mm(0.2))
    layout.addLayoutItem(patch)
    return patch

def _hilo_colors(mode, stops=None):
    """连续值图例高/低色块颜色（与渲染色带两端一致）。"""
    if mode == "carbon":
        return "#bd0026", "#ffff00"
    if mode == "habitat":
        return "#1a9850", "#d73027"
    if stops:
        return stops[-1][1], stops[0][1]
    return "#fde725", "#440154"


def _add_hilo_legend(layout, title, vmin, vmax, x, y,
                    high_color="#bd0026", low_color="#ffff00"):
    """标准图例：左下角 高/低 双色图例（无框）。"""
    fs_title, fs_body = 14, 12
    patch_sz = 10.0
    lh = 7.5
    gap_value_patch = 6.5   # 「<值>」与色块间距
    gap_patches = 6.5         # 两色块间距
    label_gap = 5.5

    y0 = y
    _add_label(layout, "图例", x, y0, 64, lh, size=fs_title, bold=True)
    y0 += lh
    _add_label(layout, title, x, y0, 76, lh, size=fs_body, bold=True)
    y0 += lh
    _add_label(layout, "<值>", x, y0, 44, 5.5, size=fs_body - 0.5)
    y0 += 5.5 + gap_value_patch

    _add_color_patch(layout, high_color, x, y0, patch_sz)
    _add_label(layout, f"高 : {vmax}", x + patch_sz + label_gap, y0 + 1.0, 56, patch_sz, size=fs_body)
    y0 += patch_sz + gap_patches

    _add_color_patch(layout, low_color, x, y0, patch_sz)
    _add_label(layout, f"低 : {vmin}", x + patch_sz + label_gap, y0 + 1, 56, patch_sz, size=fs_body)


def _add_class_legend(layout, title, classes, x, y):
    """标准图例：分类色块列表（LULC 等）。"""
    fs_title, fs_body = 14, 11
    patch_sz = 8.0
    lh = 7.0
    gap_rows = 4.0
    label_gap = 5.0

    y0 = y
    _add_label(layout, "图例", x, y0, 64, lh, size=fs_title, bold=True)
    y0 += lh
    _add_label(layout, title, x, y0, 80, lh, size=fs_body, bold=True)
    y0 += lh + 2.0

    for _val, (lbl, color) in classes.items():
        _add_color_patch(layout, color, x, y0, patch_sz)
        _add_label(layout, lbl, x + patch_sz + label_gap, y0 + 0.5, 48, patch_sz, size=fs_body)
        y0 += patch_sz + gap_rows


def _add_manual_scalebar(layout, map_w_mm, map_width_mi, right_x, y, miles_w=12.0):
    """手绘比例尺，右对齐，整体不超出内框右边界。"""
    _, bar_total_mi = _scalebar_miles_from_width(map_width_mi)
    n_seg = 4
    seg_mi = bar_total_mi / n_seg
    bar_mm = map_w_mm * (bar_total_mi / map_width_mi)
    bar_mm = max(44.0, min(bar_mm, 54.0))
    total_w = bar_mm + miles_w + 1.0
    x0 = right_x - total_w
    bar_h = 4.0
    fs = 6.5

    seg_w = bar_mm / n_seg

    for i in range(n_seg):
        box = QgsLayoutItemShape(layout)
        box.setShapeType(QgsLayoutItemShape.Rectangle)
        box.attemptMove(_pt(x0 + i * seg_w, y))
        box.attemptResize(_sz(seg_w, bar_h))
        color = "0,0,0,255" if i % 2 == 0 else "255,255,255,255"
        try:
            from qgis.core import QgsFillSymbol
            sym = QgsFillSymbol.createSimple({
                "color": color,
                "outline_color": "0,0,0,255",
                "outline_width": "0.25",
            })
            box.setSymbol(sym)
        except Exception:
            box.setBackgroundEnabled(True)
            box.setBackgroundColor(QColor("#000000" if i % 2 == 0 else "#ffffff"))
            box.setFrameEnabled(True)
            box.setFrameStrokeWidth(_mm(0.2))
        layout.addLayoutItem(box)

    for i in range(n_seg + 1):
        val = i * seg_mi
        label = str(int(val)) if abs(val - round(val)) < 0.01 else f"{val:.2f}".rstrip("0").rstrip(".")
        _add_label(layout, label, x0 + i * seg_w - 3, y - 4.5, 9, 4, size=fs, halign=Qt.AlignHCenter)

    _add_label(layout, "Miles", x0 + bar_mm + 1.5, y + 0.3, miles_w, bar_h, size=fs, bold=True)

def _scalebar_miles_from_width(width_mi):
    target_total = width_mi * 0.58
    nice_totals = [11, 16.5, 22, 27.5, 33]
    total = min(nice_totals, key=lambda x: abs(x - target_total))
    return total / 4.0, total

def _dms_label(val, axis):
    """度分秒标注；整分时省略秒，如 119°20'东。"""
    if axis == "lon":
        hemi = "东" if val >= 0 else "西"
    else:
        hemi = "北" if val >= 0 else "南"
    total_sec = int(round(abs(val) * 3600))
    d = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if s == 0:
        return f"{d}°{m}'{hemi}"
    return f"{d}°{m}'{s}\"{hemi}"

def _map_geo_bounds(mi, layer):
    """用地图实际显示范围求经纬度边界（含留白缓冲）。"""
    from qgis.core import QgsCoordinateTransform, QgsPointXY
    ext = mi.extent()
    map_crs = mi.crs() if mi.crs().isValid() else layer.crs()
    dst = QgsCoordinateReferenceSystem("EPSG:4326")
    xf = QgsCoordinateTransform(map_crs, dst, QgsProject.instance())
    pts = [
        xf.transform(QgsPointXY(ext.xMinimum(), ext.yMinimum())),
        xf.transform(QgsPointXY(ext.xMinimum(), ext.yMaximum())),
        xf.transform(QgsPointXY(ext.xMaximum(), ext.yMinimum())),
        xf.transform(QgsPointXY(ext.xMaximum(), ext.yMaximum())),
    ]
    return (
        min(p.x() for p in pts), max(p.x() for p in pts),
        min(p.y() for p in pts), max(p.y() for p in pts),
        map_crs, ext,
    )

def _frange10(vmin, vmax):
    """按 10′ 间隔生成落在 [vmin, vmax] 内的刻度。"""
    import math
    step_min = 10.0
    start = math.ceil(vmin * 60.0 / step_min - 1e-9) * step_min
    vals = []
    m = start
    n = 0
    while m <= vmax * 60.0 + 1e-9 and n < 100:
        vals.append(m / 60.0)
        m += step_min
        n += 1
    return vals

def _add_graticule_labels(layout, mi, layer, ix, iy, iw, ih, ox, oy, ow, oh, gap):
    """经纬度标注写在双线图框间隙内，位置与格网线对齐。"""
    from qgis.core import QgsCoordinateTransform, QgsPointXY
    lon_min, lon_max, lat_min, lat_max, map_crs, ext = _map_geo_bounds(mi, layer)
    geo_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    to_map = QgsCoordinateTransform(geo_crs, map_crs, QgsProject.instance())
    mid_lat = (lat_min + lat_max) / 2
    mid_lon = (lon_min + lon_max) / 2
    edge = 0.04
    fs = 7.0
    top_y = oy + gap / 2
    bot_y = iy + ih + gap / 2
    left_cx = ox + gap / 2
    right_cx = ix + iw + gap / 2

    for lon in _frange10(lon_min, lon_max):
        pt = to_map.transform(QgsPointXY(lon, mid_lat))
        frac = (pt.x() - ext.xMinimum()) / ext.width() if ext.width() else 0.5
        if frac < edge or frac > 1 - edge:
            continue
        x = ix + frac * iw
        txt = _dms_label(lon, "lon")
        _add_label(layout, txt, x - 14, top_y - 2.2, 28, 4.5, size=fs, halign=Qt.AlignHCenter)
        _add_label(layout, txt, x - 14, bot_y - 2.2, 28, 4.5, size=fs, halign=Qt.AlignHCenter)

    for lat in _frange10(lat_min, lat_max):
        pt = to_map.transform(QgsPointXY(mid_lon, lat))
        frac = (pt.y() - ext.yMinimum()) / ext.height() if ext.height() else 0.5
        if frac < edge or frac > 1 - edge:
            continue
        y = iy + ih - frac * ih
        txt = _dms_label(lat, "lat")
        # 中心锚点旋转：字顶朝向图内
        _add_label(
            layout, txt, left_cx, y, 24, 4.5,
            size=fs, halign=Qt.AlignHCenter, rotation=90,
        )
        _add_label(
            layout, txt, right_cx, y, 24, 4.5,
            size=fs, halign=Qt.AlignHCenter, rotation=-90,
        )

def _configure_grid(mi):
    """仅绘制格网线，不启用 QGIS 自带标注。"""
    g = mi.grid()
    g.setEnabled(True)
    g.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
    g.setIntervalX(10.0 / 60.0)
    g.setIntervalY(10.0 / 60.0)
    g.setStyle(0)
    try:
        from qgis.core import QgsLineSymbol
        sym = QgsLineSymbol.createSimple({"outline_color": "80,80,80,200", "outline_width": "0.1"})
        g.setLineSymbol(sym)
    except Exception:
        pass
    g.setAnnotationEnabled(False)
    g.setFrameStyle(0)
    g.setFrameWidth(0)
    return g

def _fit_map_extent(layer, map_w_mm, map_h_mm, buffer=0.10, target_crs=None, project=None):
    """按地图框宽高比扩展范围；可选变换到 target_crs（如 EPSG:4326）。"""
    from qgis.core import QgsRectangle, QgsCoordinateTransform
    ext = QgsRectangle(layer.extent())
    if target_crs is not None and target_crs.isValid() and layer.crs().isValid():
        if target_crs != layer.crs():
            xf = QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())
            ext = xf.transformBoundingBox(ext)
    ew, eh = ext.width(), ext.height()
    if ew <= 0 or eh <= 0:
        return ext
    map_ar = map_w_mm / map_h_mm
    data_ar = ew / eh
    cx = (ext.xMinimum() + ext.xMaximum()) / 2
    cy = (ext.yMinimum() + ext.yMaximum()) / 2
    if data_ar > map_ar:
        new_h = ew / map_ar
        ext.setYMinimum(cy - new_h / 2)
        ext.setYMaximum(cy + new_h / 2)
    else:
        new_w = eh * map_ar
        ext.setXMinimum(cx - new_w / 2)
        ext.setXMaximum(cx + new_w / 2)
    ext.scale(1 + buffer)
    return ext

def build_layout(project, layer, title, mode="auto", vmin=None, vmax=None, stops=None):
    """全流程统一布局：双层图框 + 间隙经纬度 + 指北针 + Miles 比例尺。
    仅图例内容按 mode 差异。
    """
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("output")

    page = layout.pageCollection().pages()[0]
    page.setPageSize("A4", QgsLayoutItemPage.Landscape)
    page.setBackgroundColor(QColor(255, 255, 255))
    PW, PH = 297.0, 210.0

    GAP = 8.0
    OUT_X, OUT_Y = 22.0, 14.0
    OUT_W, OUT_H = PW - 44.0, PH - 28.0
    IN_X, IN_Y = OUT_X + GAP, OUT_Y + GAP
    IN_W, IN_H = OUT_W - 2 * GAP, OUT_H - 2 * GAP

    outer = QgsLayoutItemShape(layout)
    outer.setShapeType(QgsLayoutItemShape.Rectangle)
    outer.attemptMove(_pt(OUT_X, OUT_Y))
    outer.attemptResize(_sz(OUT_W, OUT_H))
    outer.setFrameEnabled(True)
    outer.setFrameStrokeWidth(_mm(0.8))
    outer.setBackgroundEnabled(False)
    layout.addLayoutItem(outer)

    inner = QgsLayoutItemShape(layout)
    inner.setShapeType(QgsLayoutItemShape.Rectangle)
    inner.attemptMove(_pt(IN_X, IN_Y))
    inner.attemptResize(_sz(IN_W, IN_H))
    inner.setFrameEnabled(True)
    inner.setFrameStrokeWidth(_mm(0.35))
    inner.setBackgroundEnabled(False)
    layout.addLayoutItem(inner)

    mi = QgsLayoutItemMap(layout)
    mi.setLayers([layer])
    geo_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    try:
        mi.setCrs(geo_crs)
    except Exception:
        pass
    mi.attemptMove(_pt(IN_X, IN_Y))
    mi.attemptResize(_sz(IN_W, IN_H))
    mi.setFrameEnabled(False)
    mi.setBackgroundColor(QColor(255, 255, 255))
    mi.setExtent(_fit_map_extent(layer, IN_W, IN_H, buffer=0.08, target_crs=geo_crs))
    layout.addLayoutItem(mi)

    _configure_grid(mi)
    _add_graticule_labels(layout, mi, layer, IN_X, IN_Y, IN_W, IN_H, OUT_X, OUT_Y, OUT_W, OUT_H, GAP)

    north = QgsLayoutItemPicture(layout)
    svg = _north_svg(compass=True)
    if svg:
        north.setPicturePath(svg)
    north.attemptMove(_pt(IN_X + IN_W - 24, IN_Y + 5))
    north.attemptResize(_sz(20, 20))
    layout.addLayoutItem(north)

    if mode == "lulc":
        _add_class_legend(layout, title, LULC_CLASSES, IN_X + 12, IN_Y + IN_H - 92)
    else:
        hi, lo = _hilo_colors(mode, stops)
        _add_hilo_legend(
            layout, title,
            vmin if vmin is not None else 0,
            vmax if vmax is not None else 1,
            IN_X + 12, IN_Y + IN_H - 64,
            high_color=hi, low_color=lo,
        )

    try:
        from qgis.core import QgsDistanceArea, QgsPointXY
        da = QgsDistanceArea()
        da.setSourceCrs(
            mi.crs() if mi.crs().isValid() else layer.crs(),
            QgsProject.instance().transformContext(),
        )
        da.setEllipsoid("WGS84")
        ext = mi.extent()
        cy = (ext.yMinimum() + ext.yMaximum()) / 2
        map_width_mi = da.measureLine(
            QgsPointXY(ext.xMinimum(), cy),
            QgsPointXY(ext.xMaximum(), cy),
        ) / 1000.0 * 0.621371
    except Exception:
        map_width_mi = _map_width_miles(layer)
    _add_manual_scalebar(layout, IN_W, map_width_mi, IN_X + IN_W - 8, IN_Y + IN_H - 11)

    return layout


# ── 主流程 ────────────────────────────────────────────────────────────────────

def render(input_tif, output_png, title, mode):
    qgs = QgsApplication([], False)
    qgs.initQgis()
    _load_chinese_fonts()

    try:
        project = QgsProject.instance()
        layer = QgsRasterLayer(str(input_tif), input_tif.stem)
        if not layer.isValid():
            raise RuntimeError(f"QGIS 无法加载栅格: {input_tif}")

        # 设置渲染器，再加入 project（False = 不加入图层面板，保留渲染器设置）
        stops = YLGN
        vmin = vmax = None
        if mode == "lulc":
            layer.setRenderer(_lulc_renderer(layer))
        else:
            stats = layer.dataProvider().bandStatistics(1)
            vmin, vmax = stats.minimumValue, stats.maximumValue
            if mode == "habitat":
                stops, vmin, vmax = RDYLGN, 0.0, 1.0
            elif mode == "carbon":
                stops = CARBON_REF
                _, vmax = _percentile_bounds(layer, 0, 98)
                vmin = 0.0
            else:
                stops = VIRIDIS
            vmin, vmax = _nice_bounds(vmin, vmax)
            layer.setRenderer(_continuous_renderer(layer, stops, vmin, vmax))

        layer.setName(LAYER_LABELS.get(mode, LAYER_LABELS["auto"]))
        layer.triggerRepaint()
        project.addMapLayer(layer, False)

        layout = build_layout(project, layer, title, mode, vmin, vmax, stops)
        project.layoutManager().addLayout(layout)

        output_png.parent.mkdir(parents=True, exist_ok=True)
        tmp_png = output_png.with_suffix(".tmp.png")
        if tmp_png.exists():
            tmp_png.unlink()
        if output_png.exists():
            output_png.unlink()

        exporter = QgsLayoutExporter(layout)
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 200
        result = exporter.exportToImage(str(tmp_png), settings)
        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"QGIS 导出失败，错误码: {result}")
        import shutil
        shutil.copy2(tmp_png, output_png)
        try:
            tmp_png.unlink()
        except OSError:
            pass
        print(f"[OK] {output_png}")
    finally:
        qgs.exitQgis()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title",  default="分析结果")
    parser.add_argument("--mode",   default="auto",
                        choices=["lulc","habitat","carbon","auto"])
    args = parser.parse_args()
    if not args.input.is_file():
        raise SystemExit(f"输入文件不存在: {args.input}")
    render(args.input, args.output, args.title, args.mode)


if __name__ == "__main__":
    main()
