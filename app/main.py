from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import tempfile
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

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
    parse_power_curve,
    parse_resource_grid,
    render_map_preview,
    wind_color_palette,
)
from app.energy import calculate_annual_energy, write_annual_energy_geotiff

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="風況解析GIS変換アプリ", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
_conversion_jobs: dict[str, dict] = {}
_conversion_jobs_lock = threading.Lock()
_conversion_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wind-conversion")
_conversion_worker_count = max(1, os.cpu_count() or 1)
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


def _safe_energy_geotiff_name(
    wrg_filename: str,
    curve_filename: str,
    used_names: set[str],
) -> str:
    combined_stem = f"{Path(wrg_filename).stem}_{Path(curve_filename).stem}"
    return _safe_geotiff_name(f"{combined_stem}.wrg", used_names)


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
    progress_callback=None,
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
        return parse_resource_grid(path, selected_zone, progress_callback)
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


@app.post("/preview-power-curve")
def preview_power_curve(power_curve_file: UploadFile = File(...)) -> JSONResponse:
    if Path(power_curve_file.filename or "").suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="パワーカーブはCSVファイルを指定してください。")
    try:
        curve_speeds, curve_powers = parse_power_curve(power_curve_file.file.read())
    except MascotFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({
        "points": [
            {"wind_speed": float(speed), "power_kw": float(power)}
            for speed, power in zip(curve_speeds, curve_powers, strict=True)
        ]
    })


@app.post("/convert-wrg-energy-geotiffs")
def convert_wrg_energy_geotiffs(
    wrg_files: list[UploadFile] = File(...),
    power_curve_files: list[UploadFile] = File(...),
    utm_zones: list[int] = Form(...),
    utm_hemispheres: list[str] = Form(...),
) -> Response:
    if not power_curve_files or any(
        Path(curve.filename or "").suffix.lower() != ".csv" for curve in power_curve_files
    ):
        raise HTTPException(status_code=400, detail="パワーカーブCSVを1つ以上指定してください。")
    if len(wrg_files) != len(utm_zones) or len(wrg_files) != len(utm_hemispheres):
        raise HTTPException(status_code=400, detail="各WRGファイルのUTM zoneと半球を指定してください。")
    for uploaded_file in wrg_files:
        if Path(uploaded_file.filename or "").suffix.lower() != ".wrg":
            raise HTTPException(status_code=400, detail="発電量GeoTIFF出力には.wrgファイルのみ指定できます。")

    try:
        power_curves = [
            (
                curve.filename or f"power_curve_{index + 1}.csv",
                *parse_power_curve(curve.file.read()),
            )
            for index, curve in enumerate(power_curve_files)
        ]
    except MascotFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with tempfile.TemporaryDirectory(prefix="mascot-wrg-energy-") as temporary:
        work_dir = Path(temporary)
        archive_path = work_dir / "annual_energy_geotiffs.zip"
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
                    for curve_name, curve_speeds, curve_powers in power_curves:
                        annual_energy = calculate_annual_energy(grid, curve_speeds, curve_powers)
                        geotiff_path = work_dir / _safe_energy_geotiff_name(
                            uploaded_file.filename or "",
                            curve_name,
                            used_names,
                        )
                        write_annual_energy_geotiff(grid, geotiff_path, annual_energy)
                        archive.write(geotiff_path, geotiff_path.name)
            content = archive_path.read_bytes()
        except HTTPException:
            raise
        except MascotFormatError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:
            logger.exception("Unexpected error while creating annual energy GeoTIFFs")
            raise

    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="annual_energy_geotiffs.zip"'},
    )


def _job_update(job_id: str, **updates) -> None:
    with _conversion_jobs_lock:
        job = _conversion_jobs.get(job_id)
        if job is not None:
            job.update(updates)


def _job_file_update(job_id: str, index: int, **updates) -> None:
    with _conversion_jobs_lock:
        job = _conversion_jobs.get(job_id)
        if job is not None:
            job["files"][index].update(updates)


def _run_conversion_job(job_id: str) -> None:
    with _conversion_jobs_lock:
        job = _conversion_jobs[job_id]
        files = [item.copy() for item in job["files"]]
        inputs = [item.copy() for item in job["inputs"]]
        work_dir = Path(job["work_dir"])
        mode = job["mode"]
        power_curves = job.get("power_curves", [])
        worker_count = job["worker_count"]
    outputs: list[Path | None] = [None] * len(files)
    files_by_input: list[list[tuple[int, dict]]] = [[] for _ in inputs]
    for output_index, item in enumerate(files):
        files_by_input[item["input_index"]].append((output_index, item))

    def convert_one(input_index: int) -> None:
        source = inputs[input_index]
        output_items = files_by_input[input_index]

        def parse_progress(percent: int) -> None:
            for output_index, _item in output_items:
                _job_file_update(
                    job_id,
                    output_index,
                    stage="parsing",
                    progress=round(percent * 0.2),
                )

        try:
            for output_index, _item in output_items:
                _job_file_update(job_id, output_index, stage="parsing", progress=0)
            grid = _parse_uploaded_grid(
                Path(source["path"]),
                source["utm_zone"],
                source["utm_hemisphere"],
                parse_progress,
            )
            if mode == "energy":
                for output_index, item in output_items:
                    _job_file_update(job_id, output_index, stage="calculating", progress=20)

                    def calculation_progress(percent: int, index: int = output_index) -> None:
                        _job_file_update(
                            job_id,
                            index,
                            stage="calculating",
                            progress=20 + round(percent * 0.7),
                        )

                    curve = power_curves[item["curve_index"]]
                    values = calculate_annual_energy(
                        grid,
                        curve["speeds"],
                        curve["powers"],
                        calculation_progress,
                        workers=worker_count if len(inputs) == 1 else 1,
                    )
                    _job_file_update(job_id, output_index, stage="writing", progress=95)
                    output = work_dir / item["output_name"]
                    write_annual_energy_geotiff(
                        grid,
                        output,
                        values,
                        lambda percent, index=output_index: _job_file_update(
                            job_id,
                            index,
                            stage="writing",
                            progress=95 + round(percent * 0.05),
                        ),
                    )
                    outputs[output_index] = output
                    _job_file_update(job_id, output_index, stage="complete", progress=100)
            else:
                output_index, item = output_items[0]
                _job_file_update(job_id, output_index, stage="writing", progress=90)
                output = work_dir / item["output_name"]
                create_wind_speed_geotiff(
                    grid,
                    output,
                    lambda percent: _job_file_update(
                        job_id,
                        output_index,
                        stage="writing",
                        progress=90 + round(percent * 0.1),
                    ),
                )
                outputs[output_index] = output
                _job_file_update(job_id, output_index, stage="complete", progress=100)
        except Exception as exc:
            logger.exception("Conversion job %s failed for %s", job_id, source["name"])
            for output_index, _item in output_items:
                _job_file_update(
                    job_id,
                    output_index,
                    stage="failed",
                    progress=0,
                    error=str(exc),
                )
            raise

    try:
        _job_update(job_id, status="running", stage="analysis")
        with ThreadPoolExecutor(
            max_workers=min(worker_count, len(inputs)),
            thread_name_prefix=f"wind-{job_id[:8]}",
        ) as workers:
            futures = [workers.submit(convert_one, index) for index in range(len(inputs))]
            for future in futures:
                future.result()

        _job_update(job_id, status="packaging", stage="packaging")
        total_bytes = sum(output.stat().st_size for output in outputs if output is not None)
        archived_bytes = 0

        def archive_progress(percent: int) -> None:
            _job_update(job_id, archive_progress=percent)

        archive_path = work_dir / (
            "annual_energy_geotiffs.zip" if mode == "energy" else "wind_speed_geotiffs.zip"
        )
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for output in outputs:
                if output is None:
                    raise RuntimeError("Conversion completed without producing every GeoTIFF.")
                with output.open("rb") as source, archive.open(output.name, "w") as target:
                    while chunk := source.read(1024 * 1024):
                        target.write(chunk)
                        archived_bytes += len(chunk)
                        archive_progress(
                            round(archived_bytes / total_bytes * 100) if total_bytes else 100
                        )
        _job_update(
            job_id,
            status="complete",
            stage="complete",
            progress=100,
            archive=str(archive_path),
        )
    except Exception as exc:
        _job_update(
            job_id,
            status="failed",
            stage="failed",
            error=str(exc),
        )
        shutil.rmtree(work_dir, ignore_errors=True)


def _create_conversion_job(
    wrg_files: list[UploadFile],
    utm_zones: list[int],
    utm_hemispheres: list[str],
    mode: str,
    power_curves: list[dict] | None = None,
) -> str:
    if not wrg_files:
        raise HTTPException(status_code=400, detail="WRGファイルを1つ以上指定してください。")
    if len(wrg_files) != len(utm_zones) or len(wrg_files) != len(utm_hemispheres):
        raise HTTPException(status_code=400, detail="各WRGファイルのUTM zoneと半球を指定してください。")
    for uploaded_file in wrg_files:
        if Path(uploaded_file.filename or "").suffix.lower() != ".wrg":
            raise HTTPException(status_code=400, detail="WRG GeoTIFF出力には.wrgファイルのみ指定できます。")

    job_id = uuid.uuid4().hex
    work_dir = Path(tempfile.mkdtemp(prefix=f"mascot-{mode}-{job_id[:8]}-"))
    inputs = []
    job_files = []
    used_names: set[str] = set()
    try:
        for index, (uploaded_file, zone, hemisphere) in enumerate(
            zip(wrg_files, utm_zones, utm_hemispheres, strict=True)
        ):
            input_path = work_dir / f"input_{index}.wrg"
            with input_path.open("wb") as target:
                while chunk := uploaded_file.file.read(1024 * 1024):
                    target.write(chunk)
            inputs.append({
                "name": uploaded_file.filename or f"input_{index}.wrg",
                "path": str(input_path),
                "utm_zone": zone,
                "utm_hemisphere": hemisphere,
            })
        if mode == "energy":
            if not power_curves:
                raise HTTPException(status_code=400, detail="パワーカーブCSVを1つ以上指定してください。")
            for input_index, source in enumerate(inputs):
                for curve_index, curve in enumerate(power_curves):
                    output_name = _safe_energy_geotiff_name(
                        source["name"],
                        curve["name"],
                        used_names,
                    )
                    job_files.append({
                        "name": f"{source['name']} × {curve['name']}",
                        "output_name": output_name,
                        "input_index": input_index,
                        "curve_index": curve_index,
                        "stage": "queued",
                        "progress": 0,
                    })
        else:
            for input_index, source in enumerate(inputs):
                output_name = _safe_geotiff_name(source["name"], used_names)
                job_files.append({
                    "name": source["name"],
                    "output_name": output_name,
                    "input_index": input_index,
                    "stage": "queued",
                    "progress": 0,
                })
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise

    with _conversion_jobs_lock:
        _conversion_jobs[job_id] = {
            "status": "queued",
            "stage": "analysis",
            "progress": 0,
            "files": job_files,
            "inputs": inputs,
            "work_dir": str(work_dir),
            "mode": mode,
            "worker_count": _conversion_worker_count,
            "archive_progress": 0,
            "power_curves": power_curves or [],
        }
    _conversion_executor.submit(_run_conversion_job, job_id)
    return job_id


def _public_job_status(job_id: str) -> dict:
    with _conversion_jobs_lock:
        job = _conversion_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="変換ジョブが見つかりません。")
        files = [
            {
                key: value
                for key, value in item.items()
                if key in {"name", "stage", "progress", "error"}
            }
            for item in job["files"]
        ]
        if job["status"] == "complete":
            progress = 100
        elif job["status"] == "packaging":
            progress = 90 + round(job.get("archive_progress", 0) * 0.1)
        else:
            progress = 10 + round(sum(item["progress"] for item in files) / len(files) * 0.8)
        result = {
            "id": job_id,
            "status": job["status"],
            "stage": job["stage"],
            "progress": progress,
            "files": files,
        }
        if job.get("error"):
            result["error"] = job["error"]
        return result


@app.post("/conversion-jobs/mean-wind-speed")
def start_mean_wind_speed_job(
    wrg_files: list[UploadFile] = File(...),
    utm_zones: list[int] = Form(...),
    utm_hemispheres: list[str] = Form(...),
) -> JSONResponse:
    job_id = _create_conversion_job(wrg_files, utm_zones, utm_hemispheres, "mean")
    return JSONResponse({"id": job_id}, status_code=202)


@app.post("/conversion-jobs/annual-energy")
def start_annual_energy_job(
    wrg_files: list[UploadFile] = File(...),
    power_curve_files: list[UploadFile] = File(...),
    utm_zones: list[int] = Form(...),
    utm_hemispheres: list[str] = Form(...),
) -> JSONResponse:
    if not power_curve_files or any(
        Path(curve.filename or "").suffix.lower() != ".csv" for curve in power_curve_files
    ):
        raise HTTPException(status_code=400, detail="パワーカーブCSVを1つ以上指定してください。")
    power_curves = []
    try:
        for index, curve in enumerate(power_curve_files):
            speeds, powers = parse_power_curve(curve.file.read())
            power_curves.append({
                "name": curve.filename or f"power_curve_{index + 1}.csv",
                "speeds": speeds,
                "powers": powers,
            })
    except MascotFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id = _create_conversion_job(
        wrg_files,
        utm_zones,
        utm_hemispheres,
        "energy",
        power_curves,
    )
    return JSONResponse({"id": job_id}, status_code=202)


@app.get("/conversion-jobs/{job_id}")
def conversion_job_status(job_id: str) -> JSONResponse:
    return JSONResponse(_public_job_status(job_id))


def _remove_conversion_job(job_id: str) -> None:
    with _conversion_jobs_lock:
        job = _conversion_jobs.pop(job_id, None)
    if job:
        shutil.rmtree(job["work_dir"], ignore_errors=True)


@app.get("/conversion-jobs/{job_id}/download")
def download_conversion_job(job_id: str) -> FileResponse:
    with _conversion_jobs_lock:
        job = _conversion_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="変換ジョブが見つかりません。")
        if job["status"] != "complete":
            raise HTTPException(status_code=409, detail="変換が完了していません。")
        archive_path = Path(job["archive"])
        filename = archive_path.name
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(_remove_conversion_job, job_id),
    )
