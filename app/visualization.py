from __future__ import annotations

import io
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from pyproj import Transformer

from app.grid import (
    MascotFormatError,
    ResourceGrid,
    _source_coordinates,
    _wgs84_anchor,
)
from app.settings import (
    DEFAULT_KMZ_OPACITY_PERCENT,
    MAX_COLOR_DIVISIONS,
)


def _contour_levels(
    values: np.ndarray,
    interval: float,
    anchor: float = 0.0,
) -> np.ndarray:
    low = float(np.nanmin(values))
    high = float(np.nanmax(values))
    first = anchor + math.ceil((low - anchor - 1e-9) / interval) * interval
    if first > high:
        return np.array([], dtype=float)
    count = int(math.floor((high - first) / interval + 1e-9)) + 1
    return first + np.arange(count, dtype=float) * interval


def _wind_color_scale(
    minimum: float,
    maximum: float,
    divisions: int,
) -> tuple[np.ndarray, matplotlib.colors.ListedColormap, matplotlib.colors.BoundaryNorm]:
    boundaries = np.linspace(minimum, maximum, divisions + 1)
    base_cmap = matplotlib.colormaps["turbo"]
    colors = [base_cmap((index + 0.5) / divisions) for index in range(divisions)]
    cmap = matplotlib.colors.ListedColormap(colors, name="wind_speed_steps")
    norm = matplotlib.colors.BoundaryNorm(boundaries, cmap.N, clip=True)
    return boundaries, cmap, norm


def wind_color_palette(divisions: int) -> list[str]:
    _, color_map, _ = _wind_color_scale(0, 1, divisions)
    return [matplotlib.colors.to_hex(color) for color in color_map.colors]


def render_map_preview(
    grid: ResourceGrid,
    minimum: float,
    maximum: float,
    divisions: int,
    interval: float,
    opacity_percent: int = DEFAULT_KMZ_OPACITY_PERCENT,
    show_legend_title: bool = True,
    legend_position: str = "right",
) -> bytes:
    _validate_color_scale(minimum, maximum, divisions)
    if not math.isfinite(interval) or interval <= 0:
        raise MascotFormatError("コンター間隔は0より大きい数値を指定してください。")
    _validate_opacity(opacity_percent)
    if legend_position not in {"left", "right"}:
        raise MascotFormatError("カラーバーの位置はleftまたはrightを指定してください。")

    boundaries, color_map, color_norm = _wind_color_scale(minimum, maximum, divisions)
    levels = _contour_levels(grid.speeds, interval, minimum)
    contours = _contour_segments(grid, levels)

    figure = plt.figure(figsize=(8, 5))
    try:
        axis = figure.add_axes([0.12, 0.08, 0.72, 0.82])
        _draw_wind_overlay(axis, grid, color_map, color_norm, opacity_percent)
        line_alpha = round(opacity_percent * 255 / 100) / 255
        line_color = (32 / 255, 32 / 255, 32 / 255, line_alpha)
        for _level, segment in contours:
            axis.plot(*segment.T, color=line_color, linewidth=1.5)
        axis.set_xlim(-grid.dx / 2, (grid.nx - 0.5) * grid.dx)
        axis.set_ylim(-grid.dy / 2, (grid.ny - 0.5) * grid.dy)
        axis.set_aspect("equal", adjustable="box")
        axis.set_axis_off()
        longitude, latitude, _transformer = _wgs84_anchor(grid)
        figure.text(
            0.12,
            0.965,
            "Mean wind speed (m/s)",
            fontsize=11,
            fontweight="bold",
            color="#202124",
            visible=show_legend_title,
        )
        figure.text(
            0.12,
            0.025,
            f"WGS 84  {latitude:.5f}°N, {longitude:.5f}°E",
            fontsize=8,
            color="#555555",
        )
        colorbar_axis = figure.add_axes([0.87, 0.14, 0.045, 0.68])
        if legend_position == "left":
            axis.set_position([0.16, 0.08, 0.72, 0.82])
            colorbar_axis.set_position([0.08, 0.14, 0.045, 0.68])
        _draw_colorbar(
            colorbar_axis,
            minimum,
            maximum,
            divisions,
            opacity_percent,
        )
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=120)
        return buffer.getvalue()
    finally:
        plt.close(figure)


def _validate_color_scale(minimum: float, maximum: float, divisions: int) -> None:
    if not math.isfinite(minimum) or minimum < 0:
        raise MascotFormatError("カラーマップ下限は0以上の数値を指定してください。")
    if not math.isfinite(maximum) or maximum <= minimum:
        raise MascotFormatError("カラーマップ上限は下限より大きい数値を指定してください。")
    if not isinstance(divisions, int) or isinstance(divisions, bool):
        raise MascotFormatError("カラーマップ分割数は整数で指定してください。")
    if divisions < 1 or divisions > MAX_COLOR_DIVISIONS:
        raise MascotFormatError(
            f"カラーマップ分割数は1〜{MAX_COLOR_DIVISIONS}で指定してください。"
        )


def _validate_opacity(opacity_percent: int) -> None:
    if not isinstance(opacity_percent, int) or isinstance(opacity_percent, bool):
        raise MascotFormatError("KMZ不透明度は整数で指定してください。")
    if opacity_percent < 0 or opacity_percent > 100:
        raise MascotFormatError("KMZ不透明度は0〜100%で指定してください。")


def _contour_segments(
    grid: ResourceGrid,
    levels: np.ndarray,
) -> list[tuple[float, np.ndarray]]:
    x_values = np.arange(grid.nx, dtype=float) * grid.dx
    y_values = np.arange(grid.ny, dtype=float) * grid.dy
    masked = np.ma.masked_invalid(grid.speeds)
    segments: list[tuple[float, np.ndarray]] = []
    if levels.size:
        fig, ax = plt.subplots()
        try:
            contour_set = ax.contour(x_values, y_values, masked, levels=levels)
            for level, level_segments in zip(contour_set.levels, contour_set.allsegs):
                for segment in level_segments:
                    if len(segment) < 2:
                        continue
                    segments.append((float(level), segment))
        finally:
            plt.close(fig)
    return segments


def _write_contours(
    path: Path,
    grid: ResourceGrid,
    levels: np.ndarray,
    transformer: Transformer,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for level, segment in _contour_segments(grid, levels):
        x_values, y_values = _source_coordinates(grid, segment[:, 0], segment[:, 1])
        longitude, latitude = transformer.transform(x_values, y_values)
        features.append({
            "type": "Feature",
            "properties": {"wind_speed_m_s": level},
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [float(lon), float(lat)]
                    for lon, lat in zip(longitude, latitude)
                ],
            },
        })
    collection = {
        "type": "FeatureCollection",
        "name": "wind_speed_contours",
        "features": features,
    }
    path.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    return features


def _draw_wind_overlay(
    axis: matplotlib.axes.Axes,
    grid: ResourceGrid,
    cmap: matplotlib.colors.ListedColormap,
    norm: matplotlib.colors.BoundaryNorm,
    opacity_percent: int,
) -> None:
    axis.imshow(
        np.ma.masked_invalid(grid.speeds),
        origin="lower",
        extent=(
            -grid.dx / 2,
            (grid.nx - 0.5) * grid.dx,
            -grid.dy / 2,
            (grid.ny - 0.5) * grid.dy,
        ),
        cmap=cmap,
        norm=norm,
        alpha=opacity_percent / 100,
        interpolation="nearest",
    )


def _draw_colorbar(
    axis: matplotlib.axes.Axes,
    minimum: float,
    maximum: float,
    divisions: int,
    opacity_percent: int,
) -> None:
    boundaries, cmap, norm = _wind_color_scale(minimum, maximum, divisions)
    tick_indices = np.unique(np.linspace(0, divisions, min(divisions + 1, 11), dtype=int))
    mappable = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
    colorbar = axis.figure.colorbar(
        mappable,
        cax=axis,
        orientation="vertical",
        boundaries=boundaries,
    )
    colorbar.solids.set_alpha(opacity_percent / 100)
    colorbar.set_ticks(boundaries[tick_indices])
    colorbar.set_ticklabels([f"{tick:g}" for tick in boundaries[tick_indices]])
    colorbar.ax.tick_params(labelsize=10, length=3, colors="#202124")
    colorbar.outline.set_edgecolor("#555555")
