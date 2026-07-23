from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .data_catalog import load_catalog, project_root_from_catalog

# 边界优先读预导出的 GeoJSON，避免启动时强依赖 shapefile/rasterio
_BOUNDARIES_DIR = Path(__file__).resolve().parents[1] / "data" / "boundaries"


def _rings_from_shape(shape) -> list[list[list[float]]]:
    pts = shape.points
    if not pts:
        return []
    if not shape.parts or len(shape.parts) <= 1:
        ring = [[float(x), float(y)] for x, y in pts]
        return [ring] if len(ring) >= 3 else []

    rings: list[list[list[float]]] = []
    starts = list(shape.parts) + [len(pts)]
    for i in range(len(starts) - 1):
        part = pts[starts[i] : starts[i + 1]]
        ring = [[float(x), float(y)] for x, y in part]
        if len(ring) >= 3:
            rings.append(ring)
    return rings


def _feature_from_shape(shape, props: dict[str, Any]) -> dict[str, Any] | None:
    rings = _rings_from_shape(shape)
    if not rings:
        return None
    if len(rings) == 1:
        geometry: dict[str, Any] = {"type": "Polygon", "coordinates": [rings[0]]}
    else:
        geometry = {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}
    return {"type": "Feature", "geometry": geometry, "properties": props}


def _load_cached_boundary(region_code: str) -> dict[str, Any] | None:
    path = _BOUNDARIES_DIR / f"{region_code}.geojson"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=16)
def _load_boundary_from_shapefile(
    cache_key: str,
    shp_path: str,
    county_name: str,
    name_field: str,
    adcode: str = "",
) -> dict[str, Any]:
    import shapefile  # pyshp，仅在没有缓存 GeoJSON 时使用

    path = Path(shp_path)
    if not path.is_file():
        raise FileNotFoundError(f"边界文件不存在: {path}")

    # 自动检测编码：新版 shp 用 UTF-8，旧版用 GBK。
    # encodingErrors="replace" 可以避免个别异常字符导致整批导出中断。
    sf = None
    last_error: Exception | None = None
    for _enc in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
        try:
            _sf = shapefile.Reader(str(path), encoding=_enc, encodingErrors="replace")
            _sf.fields
            sf = _sf
            break
        except Exception as exc:
            last_error = exc
            continue
    if sf is None:
        raise ValueError(f"无法读取 shapefile（编码识别失败）: {path}; last_error={last_error}")

    field_names = [f[0] for f in sf.fields[1:]]
    if name_field not in field_names:
        for fallback in ("\u5730\u540d", "NAME99"):
            if fallback in field_names:
                name_field = fallback
                break

    # 关键修复：优先按行政区划码精确匹配，避免全国同名区一起显示
    code_fields = [f for f in ("\u533a\u5212\u7801", "ADCODE99", "code", "GID_3") if f in field_names]

    features: list[dict[str, Any]] = []
    for i, rec in enumerate(sf.records()):
        props = rec.as_dict()
        name = str(props.get(name_field, ""))

        matched = False
        if adcode and code_fields:
            for code_field in code_fields:
                if str(props.get(code_field, "")).strip() == str(adcode).strip():
                    matched = True
                    break
        else:
            # 没有 adcode 时才退回名称精确匹配；不要用 contains，避免重名区误选
            matched = name == county_name

        if not matched:
            continue

        feat = _feature_from_shape(sf.shape(i), {**props, "region_name": name})
        if feat:
            features.append(feat)

    if not features:
        raise ValueError(f"在 {path.name} 中未找到地区: {county_name} (adcode={adcode or 'N/A'})")

    return {"type": "FeatureCollection", "features": features}


def get_region_boundary_geojson(
    *,
    catalog_path: Path,
    region_code: str,
) -> dict[str, Any]:
    cached = _load_cached_boundary(region_code)
    if cached is not None:
        return cached

    catalog = load_catalog(catalog_path)
    region_cfg = catalog["regions"].get(region_code)
    if not region_cfg:
        raise ValueError(f"未注册地区: {region_code}")

    project_root = project_root_from_catalog(catalog_path)
    matches = sorted(project_root.glob(region_cfg["boundary_glob"]))
    if not matches:
        raise FileNotFoundError(region_cfg["boundary_glob"])

    county_name = region_cfg.get("county_name") or region_cfg.get("region_name") or region_code
    name_field = region_cfg.get("name_field", "NAME99")
    adcode = str(region_cfg.get("adcode", ""))
    shp_path = str(matches[0].resolve())
    cache_key = f"{shp_path}|{county_name}|{name_field}|{adcode}"
    return _load_boundary_from_shapefile(cache_key, shp_path, county_name, name_field, adcode)


def boundary_bounds(geojson: dict[str, Any]) -> list[float]:
    """Return [west, south, east, north] in WGS84."""
    coords: list[tuple[float, float]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            walk(obj.get("coordinates"))
            return
        if isinstance(obj, (list, tuple)):
            if (
                len(obj) >= 2
                and isinstance(obj[0], (int, float))
                and isinstance(obj[1], (int, float))
            ):
                coords.append((float(obj[0]), float(obj[1])))
                return
            for item in obj:
                walk(item)

    for feat in geojson.get("features", []):
        walk(feat.get("geometry"))

    if not coords:
        raise ValueError("无法从 GeoJSON 计算范围")

    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    pad_lon = max((max(lons) - min(lons)) * 0.06, 0.02)
    pad_lat = max((max(lats) - min(lats)) * 0.06, 0.02)
    return [min(lons) - pad_lon, min(lats) - pad_lat, max(lons) + pad_lon, max(lats) + pad_lat]


def raster_corners_wgs84(path: Path) -> list[list[float]]:
    """
    返回栅格四角 WGS84 坐标（Mapbox image 顺序）：
    左上、右上、右下、左下。
    投影坐标系（如 Albers）必须用四角配准，不能用轴对齐 bbox 对角点。
    """
    try:
        import rasterio
        from pyproj import Transformer
    except ImportError as exc:
        raise ImportError(
            "栅格范围计算需要 rasterio 与 pyproj，请在 backend 虚拟环境中安装："
            "pip install rasterio pyproj"
        ) from exc

    with rasterio.open(path) as src:
        b = src.bounds
        crs = src.crs
        corners_proj = [
            (b.left, b.top),
            (b.right, b.top),
            (b.right, b.bottom),
            (b.left, b.bottom),
        ]

    if crs and crs.to_epsg() != 4326:
        transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        return [
            list(transformer.transform(x, y)) for x, y in corners_proj
        ]

    return [[float(x), float(y)] for x, y in corners_proj]


def raster_bounds_wgs84(path: Path) -> list[float]:
    """Return [west, south, east, north] from four corners (for fitBounds)."""
    corners = raster_corners_wgs84(path)
    lons = [c[0] for c in corners]
    lats = [c[1] for c in corners]
    pad_lon = max((max(lons) - min(lons)) * 0.02, 0.005)
    pad_lat = max((max(lats) - min(lats)) * 0.02, 0.005)
    return [
        min(lons) - pad_lon,
        min(lats) - pad_lat,
        max(lons) + pad_lon,
        max(lats) + pad_lat,
    ]


def raster_image_coordinates(path: Path) -> list[list[float]]:
    """Mapbox image source coordinates: top-left, top-right, bottom-right, bottom-left."""
    return raster_corners_wgs84(path)
