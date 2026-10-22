from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pyproj import CRS, Transformer
from pyproj.transformer import TransformerGroup

from app.settings import DEFAULT_WRG_UTM_ZONE


class MascotFormatError(ValueError):
    pass


@dataclass
class ResourceGrid:
    nx: int
    ny: int
    dx: float
    dy: float
    sw_x: float
    sw_y: float
    sw_latitude: float
    sw_longitude: float
    speeds: np.ndarray
    coordinate_crs: CRS | None = None
    source_format: str = "mrg"
    sector_frequencies: np.ndarray | None = None
    sector_scales: np.ndarray | None = None
    sector_shapes: np.ndarray | None = None


def _number(value: str, field: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise MascotFormatError(f"ヘッダー {field} の値を数値として読み取れません。") from exc
    if not math.isfinite(result):
        raise MascotFormatError(f"ヘッダー {field} の値が不正です。")
    return result


def _dms(value: str, field: str) -> float:
    parts = re.findall(r"[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?", value)
    if len(parts) == 1:
        return _number(parts[0], field)
    if len(parts) != 3:
        raise MascotFormatError(f"ヘッダー {field} は度・分・秒の3値である必要があります。")
    degrees, minutes, seconds = (float(part) for part in parts)
    if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
        raise MascotFormatError(f"ヘッダー {field} の度・分・秒が不正です。")
    sign = -1 if degrees < 0 else 1
    return sign * (abs(degrees) + minutes / 60 + seconds / 3600)


def parse_mrg(path: str | Path) -> ResourceGrid:
    header: dict[str, str] = {}
    data_started = False
    heading_lines = 0
    records = 0
    data: np.ndarray | None = None
    seen: np.ndarray | None = None

    try:
        source = Path(path).open("r", encoding="cp932", errors="replace")
    except OSError as exc:
        raise MascotFormatError(f"入力ファイルを開けません: {exc}") from exc

    with source:
        for line_number, line in enumerate(source, start=1):
            stripped = line.strip()
            if not data_started:
                if stripped.upper() == "&DATA":
                    data_started = True
                    continue
                match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*,?\s*$", line)
                if match:
                    header[match.group(1).lower()] = match.group(2).strip()
                continue

            if stripped.startswith("/"):
                break
            if not stripped:
                continue
            if heading_lines < 2:
                heading_lines += 1
                continue

            tokens = stripped.split()
            try:
                x, y, _altitude, scale, shape = (float(token) for token in tokens[:5])
            except (ValueError, IndexError):
                if records == 0 and stripped.startswith("|"):
                    continue
                raise MascotFormatError(f"{line_number}行目の格子データを読み取れません。")

            if not all(math.isfinite(value) for value in (x, y, scale, shape)):
                raise MascotFormatError(f"{line_number}行目に有限でない数値があります。")

            if data is None:
                required = (
                    "nx", "ny", "dx", "dy", "sw_x_coordinate",
                    "sw_y_coordinate", "sw_latitude", "sw_longitude",
                )
                missing = [key for key in required if key not in header]
                if missing:
                    raise MascotFormatError(f"ヘッダーに必要な項目がありません: {', '.join(missing)}")
                nx_value = _number(header["nx"], "nx")
                ny_value = _number(header["ny"], "ny")
                if not nx_value.is_integer() or not ny_value.is_integer():
                    raise MascotFormatError("nx と ny は整数である必要があります。")
                nx = int(nx_value)
                ny = int(ny_value)
                dx = _number(header["dx"], "dx")
                dy = _number(header["dy"], "dy")
                sw_x = _number(header["sw_x_coordinate"], "SW_x_coordinate")
                sw_y = _number(header["sw_y_coordinate"], "SW_y_coordinate")
                latitude = _dms(header["sw_latitude"], "SW_latitude")
                longitude = _dms(header["sw_longitude"], "SW_longitude")
                if nx < 2 or ny < 2 or dx <= 0 or dy <= 0:
                    raise MascotFormatError("格子数または格子間隔が不正です。")
                if abs(latitude) > 90 or abs(longitude) > 180:
                    raise MascotFormatError("ヘッダーの緯度・経度が範囲外です。")
                data = np.full((ny, nx), np.nan, dtype=np.float32)
                seen = np.zeros((ny, nx), dtype=bool)

            col = round((x - sw_x) / dx)
            row = round((y - sw_y) / dy)
            tolerance_x = max(0.01, dx * 1e-4)
            tolerance_y = max(0.01, dy * 1e-4)
            if (
                col < 0 or col >= nx or row < 0 or row >= ny
                or abs(x - (sw_x + col * dx)) > tolerance_x
                or abs(y - (sw_y + row * dy)) > tolerance_y
            ):
                raise MascotFormatError(f"{line_number}行目の座標がヘッダーの格子定義と一致しません。")
            if seen[row, col]:
                raise MascotFormatError(f"{line_number}行目の格子座標が重複しています。")
            seen[row, col] = True
            records += 1
            if scale > 0 and shape > 0:
                data[row, col] = scale * math.gamma(1 + 1 / shape)

    if not data_started:
        raise MascotFormatError("&DATA セクションが見つかりません。")
    if data is None or seen is None:
        raise MascotFormatError("格子データがありません。")
    if records != nx * ny:
        raise MascotFormatError(
            f"格子データの数がヘッダーと一致しません（期待値 {nx * ny}、実際 {records}）。"
        )
    if not np.isfinite(data).any():
        raise MascotFormatError("有効なワイブルパラメーター（A > 0、k > 0）がありません。")

    return ResourceGrid(
        nx=nx,
        ny=ny,
        dx=dx,
        dy=dy,
        sw_x=sw_x,
        sw_y=sw_y,
        sw_latitude=latitude,
        sw_longitude=longitude,
        speeds=data,
    )


def parse_wrg(
    path: str | Path,
    utm_zone: str = DEFAULT_WRG_UTM_ZONE,
    progress_callback: Callable[[int], None] | None = None,
) -> ResourceGrid:
    match = re.fullmatch(r"(?:[1-9]|[1-5][0-9]|60)([NS])", utm_zone.upper())
    if match is None:
        raise MascotFormatError("WRGのUTMゾーンは1N〜60Nまたは1S〜60Sから選択してください。")
    zone_number = int(utm_zone[:-1])
    hemisphere = match.group(1)
    epsg_code = (32600 if hemisphere == "N" else 32700) + zone_number

    try:
        with Path(path).open("r", encoding="cp932", errors="replace") as source:
            lines = source.readlines()
    except OSError as exc:
        raise MascotFormatError(f"入力ファイルを開けません: {exc}") from exc

    if not lines:
        raise MascotFormatError("WRGファイルが空です。")

    try:
        header = lines[0].split()
        if len(header) < 5:
            raise ValueError
        nx_value, ny_value = float(header[0]), float(header[1])
        sw_x, sw_y, spacing = (float(value) for value in header[2:5])
    except ValueError as exc:
        raise MascotFormatError("WRGの1行目に格子数・UTM座標・格子間隔が必要です。") from exc
    if (
        not all(math.isfinite(value) for value in (nx_value, ny_value, sw_x, sw_y, spacing))
        or not nx_value.is_integer()
        or not ny_value.is_integer()
    ):
        raise MascotFormatError("WRGの格子数または座標が不正です。")
    nx, ny = int(nx_value), int(ny_value)
    if nx < 2 or ny < 2 or spacing <= 0:
        raise MascotFormatError("WRGの格子数または格子間隔が不正です。")

    data = np.full((ny, nx), np.nan, dtype=np.float32)
    seen = np.zeros((ny, nx), dtype=bool)
    sector_frequencies: np.ndarray | None = None
    sector_scales: np.ndarray | None = None
    sector_shapes: np.ndarray | None = None
    sector_count: int | None = None
    records = 0
    for line_number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        tokens = line.split()
        if len(tokens) < 7 or tokens[0].lower() != "gridpoint":
            raise MascotFormatError(f"{line_number}行目のWRG格子データを読み取れません。")
        try:
            x, y, _altitude, _height, scale, shape = (
                float(value) for value in tokens[1:7]
            )
        except ValueError as exc:
            raise MascotFormatError(f"{line_number}行目のWRG格子データを読み取れません。") from exc
        if not all(math.isfinite(value) for value in (x, y, scale, shape)):
            raise MascotFormatError(f"{line_number}行目に有限でない数値があります。")

        col = round((x - sw_x) / spacing)
        row = round((y - sw_y) / spacing)
        tolerance = max(0.01, spacing * 1e-4)
        if (
            col < 0 or col >= nx or row < 0 or row >= ny
            or abs(x - (sw_x + col * spacing)) > tolerance
            or abs(y - (sw_y + row * spacing)) > tolerance
        ):
            raise MascotFormatError(f"{line_number}行目のUTM座標がWRG格子定義と一致しません。")
        if seen[row, col]:
            raise MascotFormatError(f"{line_number}行目の格子座標が重複しています。")
        seen[row, col] = True
        records += 1
        if progress_callback is not None and (
            records % max(1, nx * ny // 100) == 0 or records == nx * ny
        ):
            progress_callback(round(records / (nx * ny) * 100))
        if scale > 0 and shape > 0:
            data[row, col] = scale * math.gamma(1 + 1 / shape)
        if len(tokens) == 7:
            if sector_count is not None:
                raise MascotFormatError(
                    f"{line_number}行目の風向別ワイブルデータが他の格子と一致しません。"
                )
            continue
        if len(tokens) < 9:
            raise MascotFormatError(f"{line_number}行目の風向別ワイブルデータを読み取れません。")
        try:
            float(tokens[7])
            count_value = float(tokens[8])
            if not math.isfinite(count_value) or not count_value.is_integer():
                raise ValueError
            point_sector_count = int(count_value)
        except ValueError as exc:
            raise MascotFormatError(
                f"{line_number}行目の風向数または風向別データが不正です。"
            ) from exc
        if point_sector_count < 1 or len(tokens) != 9 + point_sector_count * 3:
            raise MascotFormatError(
                f"{line_number}行目の風向別データ数が風向数と一致しません。"
            )
        if sector_count is None:
            sector_count = point_sector_count
            sector_frequencies = np.full((ny, nx, sector_count), np.nan, dtype=np.float64)
            sector_scales = np.full((ny, nx, sector_count), np.nan, dtype=np.float64)
            sector_shapes = np.full((ny, nx, sector_count), np.nan, dtype=np.float64)
        elif point_sector_count != sector_count:
            raise MascotFormatError(
                f"{line_number}行目の風向数が他の格子と一致しません。"
            )

        assert sector_frequencies is not None
        assert sector_scales is not None
        assert sector_shapes is not None
        try:
            directional_values = np.asarray(
                [float(value) for value in tokens[9:]],
                dtype=np.float64,
            ).reshape(sector_count, 3)
        except ValueError as exc:
            raise MascotFormatError(
                f"{line_number}行目の風向別ワイブルデータを読み取れません。"
            ) from exc
        if not np.isfinite(directional_values).all():
            raise MascotFormatError(f"{line_number}行目の風向別データに有限でない数値があります。")
        frequencies = directional_values[:, 0] / 10
        scales = directional_values[:, 1] / 10
        shapes = directional_values[:, 2] / 100
        if np.any(frequencies < 0) or np.any(
            (frequencies > 0) & ((scales <= 0) | (shapes <= 0))
        ):
            raise MascotFormatError(
                f"{line_number}行目の出現頻度または風向別ワイブルパラメーターが不正です。"
            )
        if frequencies.sum() <= 0:
            raise MascotFormatError(f"{line_number}行目に有効な風向別出現頻度がありません。")
        sector_frequencies[row, col] = frequencies
        sector_scales[row, col] = scales
        sector_shapes[row, col] = shapes

    if records != nx * ny:
        raise MascotFormatError(
            f"WRG格子データの数がヘッダーと一致しません（期待値 {nx * ny}、実際 {records}）。"
        )
    if not np.isfinite(data).any():
        raise MascotFormatError("有効なワイブルパラメーター（A > 0、k > 0）がありません。")
    if sector_count is not None and (
        sector_frequencies is None
        or sector_scales is None
        or sector_shapes is None
        or np.isnan(sector_frequencies).any()
    ):
        raise MascotFormatError("すべてのWRG格子に風向別ワイブルデータが必要です。")

    return ResourceGrid(
        nx=nx,
        ny=ny,
        dx=spacing,
        dy=spacing,
        sw_x=sw_x,
        sw_y=sw_y,
        sw_latitude=math.nan,
        sw_longitude=math.nan,
        speeds=data,
        coordinate_crs=CRS.from_epsg(epsg_code),
        source_format="wrg",
        sector_frequencies=sector_frequencies,
        sector_scales=sector_scales,
        sector_shapes=sector_shapes,
    )


def parse_resource_grid(
    path: str | Path,
    utm_zone: str = DEFAULT_WRG_UTM_ZONE,
    progress_callback: Callable[[int], None] | None = None,
) -> ResourceGrid:
    suffix = Path(path).suffix.lower()
    if suffix == ".mrg":
        return parse_mrg(path)
    if suffix == ".wrg":
        return parse_wrg(path, utm_zone, progress_callback)
    raise MascotFormatError("入力ファイルは.mrgまたは.wrgを指定してください。")


def _wgs84_anchor(grid: ResourceGrid) -> tuple[float, float, Transformer]:
    if grid.coordinate_crs is not None:
        transform = Transformer.from_crs(grid.coordinate_crs, CRS.from_epsg(4326), always_xy=True)
        longitude, latitude = transform.transform(grid.sw_x, grid.sw_y)
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            raise MascotFormatError("UTM座標をWGS 84へ変換できません。")
        return longitude, latitude, transform

    operations = TransformerGroup(
        CRS.from_epsg(4301),
        CRS.from_epsg(4326),
        always_xy=True,
    )
    if not operations.transformers:
        raise MascotFormatError("日本測地系からWGS 84への座標変換を利用できません。")
    datum_transform = operations.transformers[0]
    if datum_transform.accuracy < 0:
        raise MascotFormatError("日本測地系からWGS 84への変換精度を確認できません。")
    longitude, latitude = datum_transform.transform(grid.sw_longitude, grid.sw_latitude)
    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise MascotFormatError("日本測地系の基準点をWGS 84へ変換できません。")
    return longitude, latitude, datum_transform


def _local_crs(grid: ResourceGrid) -> CRS:
    if grid.coordinate_crs is not None:
        return grid.coordinate_crs
    longitude, latitude, _datum_transform = _wgs84_anchor(grid)
    return CRS.from_proj4(
        f"+proj=aeqd +lat_0={latitude} +lon_0={longitude} "
        "+datum=WGS84 +units=m +no_defs +type=crs"
    )


def _source_coordinates(
    grid: ResourceGrid,
    x_values: np.ndarray,
    y_values: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if grid.coordinate_crs is not None:
        return x_values + grid.sw_x, y_values + grid.sw_y
    return x_values, y_values
