from __future__ import annotations

import json
import logging
import math
import re
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.converter import (
    DEFAULT_COLOR_DIVISIONS,
    DEFAULT_COLOR_MAXIMUM,
    DEFAULT_COLOR_MINIMUM,
    DEFAULT_KMZ_OPACITY_PERCENT,
    DEFAULT_WRG_UTM_ZONE,
    MAX_COLOR_DIVISIONS,
    MascotFormatError,
    ResourceGrid,
    create_exports,
    create_wind_speed_geotiff,
    parse_resource_grid,
    render_map_preview,
    wind_color_palette,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="風況解析GIS変換アプリ", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
PAGE_TEMPLATE = (Path(__file__).parent / "templates" / "index.html").read_text(encoding="utf-8")
UTM_ZONE_OPTIONS = "\n".join(
    f'          <option value="{zone}"'
    f'{" selected" if zone == int(DEFAULT_WRG_UTM_ZONE[:-1]) else ""}>{zone}</option>'
    for zone in range(1, 61)
)


def _render_page() -> str:
    palettes = {
        "maxColorDivisions": MAX_COLOR_DIVISIONS,
        "colorPalettes": {
            divisions: wind_color_palette(divisions)
            for divisions in range(1, MAX_COLOR_DIVISIONS + 1)
        },
    }
    replacements = {
        "__UTM_ZONE_OPTIONS__": UTM_ZONE_OPTIONS,
        "__MAX_COLOR_DIVISIONS__": str(MAX_COLOR_DIVISIONS),
        "__DEFAULT_COLOR_DIVISIONS__": str(DEFAULT_COLOR_DIVISIONS),
        "__DEFAULT_KMZ_OPACITY_PERCENT__": str(DEFAULT_KMZ_OPACITY_PERCENT),
        "__DEFAULT_CONTOUR_INTERVAL__": str(
            (DEFAULT_COLOR_MAXIMUM - DEFAULT_COLOR_MINIMUM) / DEFAULT_COLOR_DIVISIONS
        ),
        "__WIND_CONFIG__": json.dumps(palettes, separators=(",", ":")),
    }
    page = PAGE_TEMPLATE
    for placeholder, value in replacements.items():
        page = page.replace(placeholder, value)
    return page


PAGE = _render_page()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return PAGE


def _safe_geotiff_name(filename: str, used_names: set[str]) -> str:
    stem = Path(filename).stem
    safe_stem = re.sub(r"[^\w.-]", "_", stem, flags=re.UNICODE).strip("._")
    if not safe_stem:
        safe_stem = "wind_speed"
    candidate = f"{safe_stem}.tif"
    suffix = 2
    while candidate.casefold() in used_names:
        candidate = f"{safe_stem}_{suffix}.tif"
        suffix += 1
    used_names.add(candidate.casefold())
    return candidate


def _resolve_contour_interval(
    interval: float,
    interval_mode: str,
    color_minimum: float,
    color_maximum: float,
    color_divisions: int,
) -> float:
    if not math.isfinite(color_minimum) or color_minimum < 0:
        raise HTTPException(status_code=400, detail="カラーマップ下限は0以上の数値を指定してください。")
    if not math.isfinite(color_maximum) or color_maximum <= color_minimum:
        raise HTTPException(status_code=400, detail="カラーマップ上限は下限より大きい数値を指定してください。")
    if color_divisions < 1 or color_divisions > MAX_COLOR_DIVISIONS:
        raise HTTPException(
            status_code=400,
            detail=f"カラーマップ分割数は1〜{MAX_COLOR_DIVISIONS}で指定してください。",
        )
    if interval_mode not in {"linked", "manual"}:
        raise HTTPException(status_code=400, detail="コンター間隔の設定方法が正しくありません。")
    if interval_mode == "linked":
        interval = (color_maximum - color_minimum) / color_divisions
    elif not math.isfinite(interval) or interval < 0.1 or interval > 100:
        raise HTTPException(status_code=400, detail="任意のコンター間隔は0.1〜100 m/sで指定してください。")
    if not math.isfinite(interval) or interval <= 0:
        raise HTTPException(status_code=400, detail="コンター間隔を正しく指定してください。")
    return interval


def _parse_uploaded_grid(
    path: Path,
    utm_zone: int,
    utm_hemisphere: str,
) -> ResourceGrid:
    selected_zone: str | None = None
    if path.suffix.lower() == ".wrg":
        hemisphere = utm_hemisphere.upper()
        if not 1 <= utm_zone <= 60 or hemisphere not in {"N", "S"}:
            raise HTTPException(
                status_code=400,
                detail="WRGのUTM zone番号は1〜60、半球はNまたはSから選択してください。",
            )
        selected_zone = f"{utm_zone}{hemisphere}"
    try:
        return parse_resource_grid(path, selected_zone)
    except MascotFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/preview")
def preview(
    mrg_file: UploadFile = File(...),
    interval: float = Form(1.0),
    interval_mode: str = Form("linked"),
    color_minimum: float = Form(DEFAULT_COLOR_MINIMUM),
    color_maximum: float = Form(DEFAULT_COLOR_MAXIMUM),
    color_divisions: int = Form(DEFAULT_COLOR_DIVISIONS),
    kmz_opacity_percent: int = Form(DEFAULT_KMZ_OPACITY_PERCENT),
    show_legend_title: bool = Form(True),
    legend_position: str = Form("right"),
    utm_zone: int = Form(int(DEFAULT_WRG_UTM_ZONE[:-1])),
    utm_hemisphere: str = Form(DEFAULT_WRG_UTM_ZONE[-1]),
) -> Response:
    suffix = Path(mrg_file.filename or "").suffix.lower()
    if suffix not in {".mrg", ".wrg"}:
        raise HTTPException(status_code=400, detail=".mrgまたは.wrgファイルを指定してください。")
    interval = _resolve_contour_interval(
        interval,
        interval_mode,
        color_minimum,
        color_maximum,
        color_divisions,
    )

    with tempfile.TemporaryDirectory(prefix="mascot-preview-") as temporary:
        input_path = Path(temporary) / f"input{suffix}"
        with input_path.open("wb") as target:
            while chunk := mrg_file.file.read(1024 * 1024):
                target.write(chunk)
        try:
            grid = _parse_uploaded_grid(input_path, utm_zone, utm_hemisphere)
            image = render_map_preview(
                grid,
                color_minimum,
                color_maximum,
                color_divisions,
                interval,
                kmz_opacity_percent,
                show_legend_title,
                legend_position,
            )
        except MascotFormatError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=image, media_type="image/png")


@app.post("/convert")
def convert(
    mrg_file: UploadFile = File(...),
    interval: float = Form(1.0),
    interval_mode: str = Form("linked"),
    color_minimum: float = Form(DEFAULT_COLOR_MINIMUM),
    color_maximum: float = Form(DEFAULT_COLOR_MAXIMUM),
    color_divisions: int = Form(DEFAULT_COLOR_DIVISIONS),
    kmz_opacity_percent: int = Form(DEFAULT_KMZ_OPACITY_PERCENT),
    show_legend_title: bool = Form(True),
    legend_position: str = Form("right"),
    utm_zone: int = Form(int(DEFAULT_WRG_UTM_ZONE[:-1])),
    utm_hemisphere: str = Form(DEFAULT_WRG_UTM_ZONE[-1]),
) -> Response:
    suffix = Path(mrg_file.filename or "").suffix.lower()
    if suffix not in {".mrg", ".wrg"}:
        raise HTTPException(status_code=400, detail=".mrgまたは.wrgファイルを指定してください。")
    interval = _resolve_contour_interval(
        interval,
        interval_mode,
        color_minimum,
        color_maximum,
        color_divisions,
    )

    with tempfile.TemporaryDirectory(prefix="mascot-wind-") as temporary:
        work_dir = Path(temporary)
        input_path = work_dir / f"input{suffix}"
        with input_path.open("wb") as target:
            while chunk := mrg_file.file.read(1024 * 1024):
                target.write(chunk)
        try:
            grid = _parse_uploaded_grid(input_path, utm_zone, utm_hemisphere)
            export_dir = work_dir / "output"
            create_exports(
                grid,
                export_dir,
                interval,
                color_minimum,
                color_maximum,
                color_divisions,
                kmz_opacity_percent,
                show_legend_title,
                legend_position,
            )
        except MascotFormatError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:
            logger.exception("Unexpected error while converting MASCOT resource grid")
            raise

        archive_path = work_dir / "mascot_wind_contours.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(export_dir.iterdir()):
                archive.write(path, path.name)
        content = archive_path.read_bytes()

    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="mascot_wind_contours.zip"'},
    )


@app.post("/convert-wrg-geotiffs")
def convert_wrg_geotiffs(
    wrg_files: list[UploadFile] = File(...),
    utm_zones: list[int] = Form(...),
    utm_hemispheres: list[str] = Form(...),
) -> Response:
    if len(wrg_files) != len(utm_zones) or len(wrg_files) != len(utm_hemispheres):
        raise HTTPException(status_code=400, detail="各WRGファイルのUTM zoneと半球を指定してください。")
    for uploaded_file in wrg_files:
        if Path(uploaded_file.filename or "").suffix.lower() != ".wrg":
            raise HTTPException(status_code=400, detail="WRG GeoTIFF出力には.wrgファイルのみ指定できます。")

    with tempfile.TemporaryDirectory(prefix="mascot-wrg-geotiff-") as temporary:
        work_dir = Path(temporary)
        archive_path = work_dir / "wind_speed_geotiffs.zip"
        used_names: set[str] = set()
        try:
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for index, (uploaded_file, zone, hemisphere) in enumerate(
                    zip(wrg_files, utm_zones, utm_hemispheres, strict=True)
                ):
                    input_path = work_dir / f"input_{index}.wrg"
                    with input_path.open("wb") as target:
                        while chunk := uploaded_file.file.read(1024 * 1024):
                            target.write(chunk)
                    grid = _parse_uploaded_grid(input_path, zone, hemisphere)
                    geotiff_path = work_dir / _safe_geotiff_name(
                        uploaded_file.filename or "",
                        used_names,
                    )
                    create_wind_speed_geotiff(grid, geotiff_path)
                    archive.write(geotiff_path, geotiff_path.name)
            content = archive_path.read_bytes()
        except HTTPException:
            raise
        except MascotFormatError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:
            logger.exception("Unexpected error while creating WRG GeoTIFFs")
            raise

    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="wind_speed_geotiffs.zip"'},
    )
