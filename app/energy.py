from __future__ import annotations

import csv
import io
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collections.abc import Callable

import numpy as np

from app.grid import MascotFormatError, ResourceGrid

ENERGY_WIND_SPEED_STEP = 0.5


def parse_power_curve(content: bytes) -> tuple[np.ndarray, np.ndarray]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("cp932")
        except UnicodeDecodeError as exc:
            raise MascotFormatError("パワーカーブCSVの文字コードを読み取れません。") from exc

    sample = "\n".join(line for line in text.splitlines() if line.strip())[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
    except csv.Error:
        delimiter = ","

    points: list[tuple[float, float]] = []
    header_skipped = False
    for line_number, row in enumerate(csv.reader(io.StringIO(text), delimiter=delimiter), start=1):
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) < 2:
            raise MascotFormatError(f"パワーカーブCSVの{line_number}行目に2列必要です。")
        try:
            speed, power = float(row[0].strip()), float(row[1].strip())
        except ValueError as exc:
            if not points and not header_skipped:
                header_skipped = True
                continue
            raise MascotFormatError(
                f"パワーカーブCSVの{line_number}行目を数値として読み取れません。"
            ) from exc
        if not math.isfinite(speed) or not math.isfinite(power) or speed < 0 or power < 0:
            raise MascotFormatError(
                f"パワーカーブCSVの{line_number}行目は0以上の有限値で指定してください。"
            )
        points.append((speed, power))

    if len(points) < 2:
        raise MascotFormatError("パワーカーブCSVには風速と出力のデータを2点以上指定してください。")
    points.sort(key=lambda point: point[0])
    if any(points[index][0] == points[index - 1][0] for index in range(1, len(points))):
        raise MascotFormatError("パワーカーブCSVで風速が重複しています。")
    return (
        np.asarray([point[0] for point in points], dtype=np.float64),
        np.asarray([point[1] for point in points], dtype=np.float64),
    )


def calculate_annual_energy(
    grid: ResourceGrid,
    curve_speeds: np.ndarray,
    curve_powers: np.ndarray,
    progress_callback: Callable[[int], None] | None = None,
    workers: int = 1,
) -> np.ndarray:
    frequencies = grid.sector_frequencies
    scales = grid.sector_scales
    shapes = grid.sector_shapes
    if frequencies is None or scales is None or shapes is None:
        raise MascotFormatError("風向別ワイブルデータを含むWRGファイルを指定してください。")
    if frequencies.shape != scales.shape or frequencies.shape != shapes.shape:
        raise MascotFormatError("WRGの風向別ワイブルデータの形状が一致しません。")

    frequency_totals = np.sum(frequencies, axis=2)
    valid_grid = frequency_totals > 0
    annual_mean_power = np.zeros(grid.speeds.shape, dtype=np.float64)
    annual_energy_conversion = 8760 / 1000
    speed_edges = np.arange(curve_speeds[0], curve_speeds[-1], ENERGY_WIND_SPEED_STEP)
    speed_edges = np.append(speed_edges, curve_speeds[-1])
    if len(speed_edges) < 2:
        speed_edges = np.asarray([curve_speeds[0], curve_speeds[-1]], dtype=np.float64)
    midpoints = (speed_edges[:-1] + speed_edges[1:]) / 2
    midpoint_powers = np.interp(midpoints, curve_speeds, curve_powers)
    sector_count = frequencies.shape[2]
    worker_count = max(1, workers)
    chunk_height = max(1, min(64, math.ceil(grid.ny / (worker_count * 4))))
    row_chunks = [
        (row_start, min(row_start + chunk_height, grid.ny))
        for row_start in range(0, grid.ny, chunk_height)
    ]

    def calculate_rows(row_start: int, row_end: int) -> np.ndarray:
        block_power = np.zeros((row_end - row_start, grid.nx), dtype=np.float64)
        for sector_index in range(sector_count):
            sector_frequency = frequencies[row_start:row_end, :, sector_index]
            active = (
                valid_grid[row_start:row_end, :]
                & (sector_frequency > 0)
            )
            if active.any():
                scale = np.where(active, scales[row_start:row_end, :, sector_index], 1.0)
                shape = np.where(active, shapes[row_start:row_end, :, sector_index], 1.0)
                expected_power = np.zeros(active.shape, dtype=np.float64)
                for index, power in enumerate(midpoint_powers):
                    lower_cdf = -np.expm1(
                        -np.power(speed_edges[index] / scale, shape)
                    )
                    upper_cdf = -np.expm1(
                        -np.power(speed_edges[index + 1] / scale, shape)
                    )
                    expected_power += power * (upper_cdf - lower_cdf)

                share = np.divide(
                    sector_frequency,
                    frequency_totals[row_start:row_end, :],
                    out=np.zeros_like(sector_frequency),
                    where=valid_grid[row_start:row_end, :],
                )
                block_power += share * expected_power
        return block_power

    completed_rows = 0
    if worker_count == 1 or len(row_chunks) == 1:
        for row_start, row_end in row_chunks:
            annual_mean_power[row_start:row_end, :] = calculate_rows(row_start, row_end)
            completed_rows += (row_end - row_start) * sector_count
            if progress_callback is not None:
                progress_callback(round(completed_rows / (sector_count * grid.ny) * 100))
    else:
        with ThreadPoolExecutor(max_workers=min(worker_count, len(row_chunks))) as executor:
            futures = {
                executor.submit(calculate_rows, row_start, row_end): (row_start, row_end)
                for row_start, row_end in row_chunks
            }
            for future in as_completed(futures):
                row_start, row_end = futures[future]
                annual_mean_power[row_start:row_end, :] = future.result()
                completed_rows += (row_end - row_start) * sector_count
                if progress_callback is not None:
                    progress_callback(round(completed_rows / (sector_count * grid.ny) * 100))

    annual_energy = annual_mean_power * annual_energy_conversion
    annual_energy[~valid_grid] = np.nan
    return annual_energy.astype(np.float32)


def write_annual_energy_geotiff(
    grid: ResourceGrid,
    output_path: str | Path,
    annual_energy: np.ndarray,
    progress_callback: Callable[[int], None] | None = None,
) -> Path:
    from app.exports import _write_geotiff

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_geotiff(
        grid,
        path,
        values=annual_energy,
        band_description="Gross annual energy production (MWh/year)",
        additional_tags={
            "quantity": "gross_annual_energy_production",
            "unit": "MWh/year",
            "assumptions": "No availability, electrical, or wake losses",
            "annual_hours": "8760",
            "hub_height": "Same as WRG reference height",
        },
        progress_callback=progress_callback,
    )
    return path
