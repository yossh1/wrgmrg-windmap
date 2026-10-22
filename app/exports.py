from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.transform import from_origin

from app.grid import (
    MascotFormatError,
    ResourceGrid,
    _local_crs,
    _source_coordinates,
    _wgs84_anchor,
)
from app.settings import (
    DEFAULT_COLOR_DIVISIONS,
    DEFAULT_COLOR_MAXIMUM,
    DEFAULT_COLOR_MINIMUM,
    DEFAULT_KMZ_OPACITY_PERCENT,
)
from app.visualization import (
    _contour_levels,
    _draw_colorbar,
    _draw_wind_overlay,
    _validate_color_scale,
    _validate_opacity,
    _wind_color_scale,
    _write_contours,
)


def _write_qml(path: Path, minimum: float, maximum: float, divisions: int) -> None:
    boundaries, cmap, _norm = _wind_color_scale(minimum, maximum, divisions)
    renderer = ET.Element("qgis", {"version": "3.34.0", "styleCategories": "Symbology"})
    pipe = ET.SubElement(renderer, "pipe")
    raster = ET.SubElement(
        pipe,
        "rasterrenderer",
        {
            "type": "singlebandpseudocolor",
            "band": "1",
            "opacity": "1",
            "alphaBand": "-1",
            "classificationMin": f"{boundaries[0]:.6f}",
            "classificationMax": f"{boundaries[-1]:.6f}",
        },
    )
    ET.SubElement(raster, "rasterTransparency")
    shader = ET.SubElement(ET.SubElement(raster, "rastershader"), "colorrampshader", {
        "colorRampType": "DISCRETE",
        "classificationMode": "1",
        "clip": "0",
        "minimumValue": f"{boundaries[0]:.6f}",
        "maximumValue": f"{boundaries[-1]:.6f}",
    })
    for index, value in enumerate(boundaries):
        color_index = min(index, divisions - 1)
        red, green, blue, _alpha = cmap(color_index)
        color = f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"
        label = (
            f"{value:g} m/s"
            if index == divisions
            else f"{value:g}–{boundaries[index + 1]:g} m/s"
        )
        ET.SubElement(shader, "item", {
            "alpha": "255",
            "value": f"{value:.6f}",
            "label": label,
            "color": color,
        })
    path.write_bytes(ET.tostring(renderer, encoding="utf-8", xml_declaration=True))


def _write_legend_bar(
    path: Path,
    minimum: float,
    maximum: float,
    divisions: int,
    opacity_percent: int,
) -> None:
    fig = plt.figure(figsize=(0.8, 4.13), dpi=150)
    fig.patch.set_facecolor("white")
    fig.patch.set_edgecolor("#444444")
    fig.patch.set_linewidth(1.2)
    try:
        colorbar_axis = fig.add_axes([0.08, 0.06, 0.40, 0.88])
        _draw_colorbar(colorbar_axis, minimum, maximum, divisions, opacity_percent)
        fig.savefig(path, dpi=150, transparent=False, pad_inches=0.01)
    finally:
        plt.close(fig)


def _write_legend_title(path: Path) -> None:
    fig = plt.figure(figsize=(8, 0.45), dpi=150)
    fig.patch.set_alpha(0)
    try:
        fig.text(
            0.04,
            0.12,
            "Mean wind speed (m/s)",
            fontsize=16,
            fontweight="bold",
            color="#202124",
        )
        fig.savefig(path, dpi=150, transparent=True, pad_inches=0.01)
    finally:
        plt.close(fig)


def _write_kmz(
    path: Path,
    png_path: Path,
    legend_path: Path,
    legend_title_path: Path,
    show_legend_title: bool,
    grid: ResourceGrid,
    transformer: Transformer,
    levels: np.ndarray,
    features: list[dict[str, Any]],
    opacity_percent: int,
    legend_position: str,
) -> None:
    west_x = -grid.dx / 2
    east_x = (grid.nx - 0.5) * grid.dx
    south_y = -grid.dy / 2
    north_y = (grid.ny - 0.5) * grid.dy
    corner_x = [west_x, east_x, east_x, west_x]
    corner_y = [south_y, south_y, north_y, north_y]
    source_x, source_y = _source_coordinates(
        grid,
        np.asarray(corner_x),
        np.asarray(corner_y),
    )
    longitudes, latitudes = transformer.transform(source_x, source_y)

    kml = ET.Element("kml", {"xmlns": "http://www.opengis.net/kml/2.2"})
    document = ET.SubElement(kml, "Document")
    ET.SubElement(document, "name").text = "MASCOT 平均風速コンター"
    overlay = ET.SubElement(document, "GroundOverlay")
    ET.SubElement(overlay, "name").text = "ワイブル分布から算出した平均風速"
    ET.SubElement(overlay, "drawOrder").text = "1"
    ET.SubElement(overlay, "Icon")
    overlay.find("Icon").append(ET.Element("href"))
    overlay.find("Icon/href").text = "wind_speed.png"
    ET.SubElement(overlay, "altitude").text = "0"
    ET.SubElement(overlay, "altitudeMode").text = "absolute"
    box = ET.SubElement(overlay, "LatLonBox")
    ET.SubElement(box, "north").text = f"{max(latitudes):.10f}"
    ET.SubElement(box, "south").text = f"{min(latitudes):.10f}"
    ET.SubElement(box, "east").text = f"{max(longitudes):.10f}"
    ET.SubElement(box, "west").text = f"{min(longitudes):.10f}"

    def add_legend_overlay(
        name: str,
        href: str,
        draw_order: int,
        overlay_x: str,
        screen_x: str,
        screen_y: str,
        size_x: str,
        size_y: str,
    ) -> None:
        overlay_element = ET.SubElement(document, "ScreenOverlay")
        ET.SubElement(overlay_element, "name").text = name
        ET.SubElement(overlay_element, "drawOrder").text = str(draw_order)
        icon = ET.SubElement(overlay_element, "Icon")
        ET.SubElement(icon, "href").text = href
        ET.SubElement(overlay_element, "overlayXY", {
            "x": overlay_x,
            "y": "1",
            "xunits": "fraction",
            "yunits": "fraction",
        })
        ET.SubElement(overlay_element, "screenXY", {
            "x": screen_x,
            "y": screen_y,
            "xunits": "fraction",
            "yunits": "fraction",
        })
        ET.SubElement(overlay_element, "size", {
            "x": size_x,
            "y": size_y,
            "xunits": "fraction",
            "yunits": "fraction",
        })

    if show_legend_title:
        add_legend_overlay(
            "平均風速凡例タイトル",
            "wind_legend_title.png",
            3,
            "0",
            "0.21",
            "0.985",
            "0.32",
            "0",
        )
    add_legend_overlay(
        "平均風速カラーバー（m/s）",
        "wind_legend.png",
        2,
        "0" if legend_position == "right" else "1",
        "0.78" if legend_position == "right" else "0.213",
        "0.955",
        "0.05",
        "0.55",
    )

    style = ET.SubElement(document, "Style", {"id": "contour"})
    line_style = ET.SubElement(style, "LineStyle")
    alpha = round(opacity_percent * 255 / 100)
    ET.SubElement(line_style, "color").text = f"{alpha:02x}202020"
    ET.SubElement(line_style, "width").text = "1.5"
    contour_folder = ET.SubElement(document, "Folder")
    ET.SubElement(contour_folder, "name").text = "風速コンター（m/s）"
    for feature in features:
        placemark = ET.SubElement(contour_folder, "Placemark")
        value = feature["properties"]["wind_speed_m_s"]
        ET.SubElement(placemark, "name").text = f"{value:g} m/s"
        ET.SubElement(placemark, "styleUrl").text = "#contour"
        coordinates = " ".join(
            f"{lon:.10f},{lat:.10f},0" for lon, lat in feature["geometry"]["coordinates"]
        )
        line_string = ET.SubElement(placemark, "LineString")
        ET.SubElement(line_string, "altitudeMode").text = "absolute"
        coordinates_element = ET.SubElement(line_string, "coordinates")
        coordinates_element.text = coordinates
    if levels.size == 0:
        ET.SubElement(contour_folder, "description").text = "指定間隔のコンターはありません。"

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", ET.tostring(kml, encoding="utf-8", xml_declaration=True))
        archive.write(png_path, "wind_speed.png")
        archive.write(legend_path, "wind_legend.png")
        if show_legend_title:
            archive.write(legend_title_path, "wind_legend_title.png")


def _write_geotiff(
    grid: ResourceGrid,
    path: Path,
    color_minimum: float | None = None,
    color_maximum: float | None = None,
    color_divisions: int | None = None,
    opacity_percent: int | None = None,
) -> None:
    longitude, latitude, datum_transform = _wgs84_anchor(grid)
    crs = _local_crs(grid)
    origin_x = grid.sw_x if grid.coordinate_crs is not None else 0.0
    origin_y = grid.sw_y if grid.coordinate_crs is not None else 0.0
    transform = from_origin(
        origin_x - grid.dx / 2,
        origin_y + (grid.ny - 0.5) * grid.dy,
        grid.dx,
        grid.dy,
    )
    source_datum = (
        f"{grid.coordinate_crs.name} (EPSG:{grid.coordinate_crs.to_epsg()})"
        if grid.coordinate_crs is not None
        else "Tokyo Datum (EPSG:4301)"
    )
    tags = {
        "wind_speed_formula": "A * Gamma(1 + 1/k)",
        "source": f"MASCOT .{grid.source_format} all-directions Weibull A and k",
        "source_format": grid.source_format,
        "source_horizontal_datum": source_datum,
        "output_horizontal_datum": "WGS 84 (EPSG:4326)",
        "datum_transform": datum_transform.description,
        "datum_transform_accuracy_m": str(datum_transform.accuracy),
        "sw_latitude": f"{latitude:.10f}",
        "sw_longitude": f"{longitude:.10f}",
    }
    if (
        color_minimum is not None
        and color_maximum is not None
        and color_divisions is not None
        and opacity_percent is not None
    ):
        tags.update(
            wind_color_minimum_m_s=str(color_minimum),
            wind_color_maximum_m_s=str(color_maximum),
            wind_color_divisions=str(color_divisions),
            wind_color_step_m_s=str((color_maximum - color_minimum) / color_divisions),
            kmz_opacity_percent=str(opacity_percent),
        )

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=grid.ny,
        width=grid.nx,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=np.nan,
        compress="deflate",
        predictor=3,
    ) as dataset:
        dataset.write(grid.speeds[::-1, :], 1)
        dataset.set_band_description(1, "Weibull mean wind speed (m/s)")
        dataset.update_tags(**tags)


def create_wind_speed_geotiff(grid: ResourceGrid, output_path: str | Path) -> Path:
    """Write an unstyled GeoTIFF containing mean wind speed in m/s."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_geotiff(grid, path)
    return path


def create_exports(
    grid: ResourceGrid,
    output_dir: str | Path,
    interval: float,
    color_minimum: float = DEFAULT_COLOR_MINIMUM,
    color_maximum: float = DEFAULT_COLOR_MAXIMUM,
    color_divisions: int = DEFAULT_COLOR_DIVISIONS,
    kmz_opacity_percent: int = DEFAULT_KMZ_OPACITY_PERCENT,
    show_legend_title: bool = True,
    legend_position: str = "right",
) -> Path:
    if not math.isfinite(interval) or interval <= 0:
        raise MascotFormatError("コンター間隔は0より大きい数値を指定してください。")
    _validate_color_scale(color_minimum, color_maximum, color_divisions)
    _validate_opacity(kmz_opacity_percent)
    if legend_position not in {"left", "right"}:
        raise MascotFormatError("カラーバーの位置はleftまたはrightを指定してください。")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    local_crs = _local_crs(grid)
    to_wgs84 = Transformer.from_crs(local_crs, CRS.from_epsg(4326), always_xy=True)
    color_boundaries, color_map, color_norm = _wind_color_scale(
        color_minimum,
        color_maximum,
        color_divisions,
    )
    levels = _contour_levels(grid.speeds, interval, color_minimum)

    raster_path = output / "wind_speed.tif"
    _write_geotiff(
        grid,
        raster_path,
        color_minimum,
        color_maximum,
        color_divisions,
        kmz_opacity_percent,
    )

    qml_path = output / "wind_speed.qml"
    _write_qml(qml_path, color_minimum, color_maximum, color_divisions)
    contours_path = output / "wind_speed_contours.geojson"
    features = _write_contours(contours_path, grid, levels, to_wgs84)

    png_path = output / "wind_speed.png"
    legend_path = output / "wind_legend.png"
    legend_title_path = output / "wind_legend_title.png"
    _write_legend_bar(
        legend_path,
        color_minimum,
        color_maximum,
        color_divisions,
        kmz_opacity_percent,
    )
    _write_legend_title(legend_title_path)
    fig = plt.figure(figsize=(8, 8), dpi=150)
    try:
        ax = fig.add_axes([0, 0, 1, 1])
        _draw_wind_overlay(ax, grid, color_map, color_norm, kmz_opacity_percent)
        ax.set_axis_off()
        fig.savefig(png_path, dpi=150, transparent=True, pad_inches=0)
    finally:
        plt.close(fig)

    kmz_path = output / "wind_speed.kmz"
    _write_kmz(
        kmz_path,
        png_path,
        legend_path,
        legend_title_path,
        show_legend_title,
        grid,
        to_wgs84,
        levels,
        features,
        kmz_opacity_percent,
        legend_position,
    )
    png_path.unlink()
    legend_path.unlink()
    legend_title_path.unlink()

    return raster_path
