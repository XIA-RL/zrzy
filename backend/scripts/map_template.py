#!/usr/bin/env python3
"""
共用制图模板。

所有地图统一布局：
  - 图框（黑色细线边框，标题居中置顶）
  - 左上角：指北针（箭头 + N 字）
  - 左下角：图例（离散色块 或 连续色带）
  - 右下角：黑白相间比例尺
  - 中间：栅格地图 + 经纬度坐标轴

外部调用：
    from map_template import MapFigure, set_chinese_font

    set_chinese_font()
    fig = MapFigure(title="安吉县碳储量分布")
    fig.draw_raster(data, extent, crs_proj, cmap="YlGn")
    fig.draw_colorbar_legend(label="碳储量 (MgC/pixel)", cmap="YlGn", vmin=0, vmax=120)
    fig.draw_discrete_legend(handles)      # 离散图例（LULC 用）
    fig.save("output.png")
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colorbar import ColorbarBase
from matplotlib.colors import Normalize
from matplotlib.figure import Figure
from pyproj import Transformer


# ── 字体 ──────────────────────────────────────────────────────────────────────

def set_chinese_font() -> None:
    """加载 Windows 中文字体，按优先级依次尝试。"""
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\STZHONGS.TTF",
    ]
    for fp in candidates:
        if Path(fp).is_file():
            from matplotlib import font_manager
            font_manager.fontManager.addfont(fp)
            prop = font_manager.FontProperties(fname=fp)
            plt.rcParams["font.family"] = prop.get_name()
            plt.rcParams["axes.unicode_minus"] = False
            return
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


# ── 经纬度格式化 ──────────────────────────────────────────────────────────────

def _dms(axis: str):
    def _fmt(v, _pos):
        hemi = ("E" if v >= 0 else "W") if axis == "lon" else ("N" if v >= 0 else "S")
        v = abs(v)
        d = int(v)
        m = int((v - d) * 60)
        s = int(round(((v - d) * 60 - m) * 60))
        if s == 60:
            s = 0; m += 1
        if m == 60:
            m = 0; d += 1
        return f"{d}°{m}'{s}\"{hemi}"
    return _fmt


# ── 地图元素绘制 ──────────────────────────────────────────────────────────────

def _draw_north_arrow(ax) -> None:
    """左上角指北针：实心箭头 + N 字。"""
    kw = dict(xycoords="axes fraction", clip_on=False, zorder=10)
    # 箭头主体（朝上）
    ax.annotate(
        "",
        xy=(0.055, 0.945), xytext=(0.055, 0.845),
        textcoords="axes fraction",
        arrowprops=dict(
            arrowstyle="-|>",
            mutation_scale=16,
            fc="black", ec="black",
            lw=1.5,
        ),
        **kw,
    )
    # N 字
    ax.text(
        0.055, 0.965, "N",
        transform=ax.transAxes,
        ha="center", va="bottom",
        fontsize=11, fontweight="bold",
        clip_on=False, zorder=10,
    )


def _draw_scale_bar(ax, geo_extent_deg: tuple[float, float, float, float]) -> None:
    """右下角黑白相间比例尺（单位 km，根据地图实际跨度自动选档）。

    geo_extent_deg: (lon_min, lon_max, lat_min, lat_max) in degrees
    """
    lon_min, lon_max, lat_min, lat_max = geo_extent_deg
    mid_lat = (lat_min + lat_max) / 2.0

    # 1 度经度 ≈ cos(lat) * 111.32 km
    km_per_deg_lon = np.cos(np.radians(mid_lat)) * 111.32
    map_width_km = (lon_max - lon_min) * km_per_deg_lon

    # 选合适的比例尺总长：约占地图宽度 30-35%
    target_km = map_width_km * 0.32
    nice = [1, 2, 5, 10, 20, 25, 50, 100, 150, 200]
    bar_km = min(nice, key=lambda x: abs(x - target_km))
    n_seg = 4
    seg_km = bar_km / n_seg

    # 比例尺在坐标轴分数中的位置（右下角）
    x_right = 0.97
    bar_frac = bar_km / map_width_km  # 比例尺占地图宽度分数
    x_left = x_right - bar_frac
    y_bar = 0.055
    y_tick = 0.070
    y_label = 0.040
    y_unit = 0.085

    for i in range(n_seg):
        x0 = x_left + i * (x_right - x_left) / n_seg
        x1 = x_left + (i + 1) * (x_right - x_left) / n_seg
        fc = "black" if i % 2 == 0 else "white"
        rect = mpatches.FancyBboxPatch(
            (x0, y_bar - 0.008), x1 - x0, 0.016,
            boxstyle="square,pad=0",
            facecolor=fc, edgecolor="black", linewidth=0.8,
            transform=ax.transAxes, clip_on=False, zorder=10,
        )
        ax.add_patch(rect)

    # 刻度数字
    for i in range(n_seg + 1):
        xf = x_left + i * (x_right - x_left) / n_seg
        val = int(i * seg_km)
        ax.text(
            xf, y_label, str(val),
            transform=ax.transAxes,
            ha="center", va="top", fontsize=7, clip_on=False, zorder=10,
        )

    # 单位
    ax.text(
        (x_left + x_right) / 2, y_unit, "km",
        transform=ax.transAxes,
        ha="center", va="bottom", fontsize=8, fontweight="bold",
        clip_on=False, zorder=10,
    )


def _set_geo_ticks(ax, proj_extent, crs_proj: str) -> None:
    """设置经纬度坐标刻度。"""
    xmin, xmax, ymin, ymax = proj_extent
    to_geo = Transformer.from_crs(crs_proj, "EPSG:4326", always_xy=True)

    xs = np.linspace(xmin, xmax, 5)
    ys = np.linspace(ymin, ymax, 6)
    lons = [to_geo.transform(x, (ymin + ymax) / 2)[0] for x in xs]
    lats = [to_geo.transform((xmin + xmax) / 2, y)[1] for y in ys]

    ax.set_xticks(xs)
    ax.set_yticks(ys)
    ax.set_xticklabels([_dms("lon")(v, 0) for v in lons], fontsize=7.5)
    ax.set_yticklabels([_dms("lat")(v, 0) for v in lats], fontsize=7.5)
    ax.tick_params(axis="both", direction="out", length=4, width=0.9, pad=5)
    for spine in ax.spines.values():
        spine.set_linewidth(1.4)

    return lons, lats  # 供比例尺计算用


# ── MapFigure ─────────────────────────────────────────────────────────────────

class MapFigure:
    """统一布局的地图画布。

    布局（figure 坐标，原点左下）：
      标题区：顶部
      地图区：[0.12, 0.10, 0.84, 0.82]  —— 留出四周给坐标轴刻度
      图例区：左下角，在地图外侧 figure 空间里
      指北针：地图左上角内侧
      比例尺：地图右下角内侧
    """

    # 地图 axes 在 figure 中的位置
    _MAP_RECT  = [0.14, 0.10, 0.80, 0.82]

    def __init__(self, title: str = "", figsize=(11, 9), dpi=150) -> None:
        import matplotlib
        matplotlib.use("Agg")

        self.fig: Figure = plt.figure(figsize=figsize, dpi=dpi, facecolor="white")
        self.ax_map = self.fig.add_axes(self._MAP_RECT)

        # 图框（标题置于图框顶边正上方）
        self.fig.text(
            0.5, 0.965, title,
            ha="center", va="bottom",
            fontsize=13, fontweight="bold",
            transform=self.fig.transFigure,
        )

        # 外图框线
        border = mpatches.FancyBboxPatch(
            (0.01, 0.01), 0.98, 0.97,
            boxstyle="square,pad=0",
            linewidth=1.5, edgecolor="black", facecolor="none",
            transform=self.fig.transFigure, clip_on=False, zorder=20,
        )
        self.fig.add_artist(border)

        self._geo_extent: tuple | None = None  # (lon_min, lon_max, lat_min, lat_max)

    # ── 栅格绘制 ──────────────────────────────────────────────────────────────

    def draw_raster(
        self,
        data: np.ndarray,
        proj_extent: tuple,        # (left, right, bottom, top) in projected CRS
        crs_proj: str,
        cmap="viridis",
        norm=None,
        pad: float = 0.04,
    ) -> None:
        left, right, bottom, top = proj_extent
        dx = (right - left) * pad
        dy = (top - bottom) * pad

        self.ax_map.imshow(
            data, origin="upper",
            extent=(left, right, bottom, top),
            cmap=cmap, norm=norm,
            interpolation="nearest",
        )
        self.ax_map.set_xlim(left - dx, right + dx)
        self.ax_map.set_ylim(bottom - dy, top + dy)
        self.ax_map.set_aspect("equal", adjustable="box")

        lons, lats = _set_geo_ticks(self.ax_map, (left, right, bottom, top), crs_proj)
        self._geo_extent = (min(lons), max(lons), min(lats), max(lats))

        _draw_north_arrow(self.ax_map)
        if self._geo_extent:
            _draw_scale_bar(self.ax_map, self._geo_extent)

    # ── 连续色带图例（左下角） ────────────────────────────────────────────────

    def draw_colorbar_legend(
        self,
        label: str,
        cmap: str,
        vmin: float,
        vmax: float,
        legend_title: str = "图例",
    ) -> None:
        # 图例区放在地图左下角内侧
        # ax_map 在 figure 里的位置是 _MAP_RECT，色带放在其左下角内侧
        map_l, map_b, map_w, map_h = self._MAP_RECT
        cb_l = map_l + 0.015
        cb_b = map_b + 0.04
        cb_w = 0.025
        cb_h = 0.22

        ax_cb = self.fig.add_axes([cb_l, cb_b, cb_w, cb_h])
        norm = Normalize(vmin=vmin, vmax=vmax)
        cb = ColorbarBase(ax_cb, cmap=plt.get_cmap(cmap),
                          norm=norm, orientation="vertical")
        cb.ax.tick_params(labelsize=7)
        ax_cb.set_title(legend_title + "\n" + label,
                        fontsize=8, pad=4, loc="left")

    # ── 离散色块图例（左下角，LULC 用） ──────────────────────────────────────

    def draw_discrete_legend(
        self,
        handles: list,
        legend_title: str = "图例",
    ) -> None:
        map_l, map_b, map_w, map_h = self._MAP_RECT
        # 在地图内部左下角放图例框
        self.ax_map.legend(
            handles=handles,
            title=legend_title,
            loc="lower left",
            bbox_to_anchor=(0.01, 0.01),
            frameon=True,
            framealpha=0.9,
            edgecolor="black",
            fontsize=8.5,
            title_fontsize=9,
        )

    # ── 保存 ─────────────────────────────────────────────────────────────────

    def save(self, output_path: Path | str, dpi: int = 150) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.fig.savefig(
            output_path, dpi=dpi,
            facecolor="white",
            bbox_inches="tight",
            pad_inches=0.05,
        )
        plt.close(self.fig)
        print(f"[OK] {output_path}")
