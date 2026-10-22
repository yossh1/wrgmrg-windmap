import io
import json
import math
from pathlib import Path
import time
import zipfile
from xml.etree import ElementTree as ET

import numpy as np
import pytest
import rasterio
from matplotlib.image import imread
from pyproj import CRS, Transformer
from pyproj.transformer import TransformerGroup
from fastapi.testclient import TestClient

from app.converter import (
    DEFAULT_COLOR_DIVISIONS,
    DEFAULT_KMZ_OPACITY_PERCENT,
    DEFAULT_WRG_UTM_ZONE,
    MAX_COLOR_DIVISIONS,
    MascotFormatError,
    _contour_levels,
    calculate_annual_energy,
    create_exports,
    create_wind_speed_geotiff,
    parse_power_curve,
    parse_mrg,
    parse_resource_grid,
    parse_wrg,
    render_map_preview,
)
from app.main import _conversion_jobs, _conversion_jobs_lock, _public_job_status, app


def make_mrg(path: Path, rows: list[str], nx: int = 2, ny: int = 2) -> None:
    path.write_text(
        "\n".join([
            "&mascot_resource_grid",
            "ver=5.0,",
            "SW_latitude= 39.00 52.00 37.7614,",
            "SW_longitude= 141.00 27.00 19.8235,",
            "SW_x_coordinate= -3000.0,",
            "SW_y_coordinate= -3000.0,",
            f"nx={nx},",
            f"ny={ny},",
            "dx=25.0,",
            "dy=25.0,",
            "Height=84.0,",
            "n_wind_direction=16,",
            "/",
            "&DATA",
            "| direction header |",
            "| columns |",
            *rows,
            "/",
        ]),
        encoding="cp932",
    )


def make_wrg(path: Path) -> None:
    path.write_text(
        "\n".join([
            "3 2 403077.909 4696286.109 100.0",
            "GridPoint 403077.909 4696286.109 0.0 104.0 9.26 1.95",
            "GridPoint 403177.909 4696286.109 0.0 104.0 9.24 1.95",
            "GridPoint 403277.909 4696286.109 0.0 104.0 9.22 1.94",
            "GridPoint 403077.909 4696386.109 0.0 104.0 9.28 1.95",
            "GridPoint 403177.909 4696386.109 0.0 104.0 9.26 1.95",
            "GridPoint 403277.909 4696386.109 0.0 104.0 9.24 1.94",
        ]),
        encoding="cp932",
    )


def make_directional_wrg(
    path: Path,
    sector_values: list[tuple[int, int, int]],
) -> None:
    rows = ["2 2 403000 4696000 100"]
    for y in (4696000, 4696100):
        for x in (403000, 403100):
            sector_data = " ".join(
                str(value)
                for frequency, scale, shape in sector_values
                for value in (frequency, scale, shape)
            )
            rows.append(
                f"GridPoint {x} {y} 0 100 10 2 0 {len(sector_values)} {sector_data}"
            )
    path.write_text("\n".join(rows), encoding="ascii")


def test_parse_mrg_calculates_weibull_mean_and_places_grid(tmp_path: Path) -> None:
    path = tmp_path / "grid.mrg"
    make_mrg(path, [
        "-3000 -3000 100 7.26 2.14",
        "-3000 -2975 101 8 2",
        "-2975 -3000 102 6 2",
        "-2975 -2975 103 5 2",
    ])

    grid = parse_mrg(path)

    assert grid.speeds.shape == (2, 2)
    assert grid.speeds[0, 0] == pytest.approx(7.26 * math.gamma(1 + 1 / 2.14))
    assert grid.speeds[1, 0] == pytest.approx(8 * math.gamma(1.5))
    assert grid.speeds[0, 1] == pytest.approx(6 * math.gamma(1.5))
    assert grid.sw_latitude == pytest.approx(39 + 52 / 60 + 37.7614 / 3600)


def test_parse_mrg_rejects_missing_grid_point(tmp_path: Path) -> None:
    path = tmp_path / "incomplete.mrg"
    make_mrg(path, [
        "-3000 -3000 100 7.26 2.14",
        "-3000 -2975 101 8 2",
        "-2975 -3000 102 6 2",
    ])

    with pytest.raises(MascotFormatError, match="格子データの数"):
        parse_mrg(path)


def test_parse_wrg_reads_utm_grid_and_weibull_parameters(tmp_path: Path) -> None:
    path = tmp_path / "wind.wrg"
    make_wrg(path)

    grid = parse_wrg(path, "54N")

    assert grid.speeds.shape == (2, 3)
    assert grid.speeds[0, 0] == pytest.approx(9.26 * math.gamma(1 + 1 / 1.95))
    assert grid.speeds[1, 2] == pytest.approx(9.24 * math.gamma(1 + 1 / 1.94))
    assert grid.coordinate_crs is not None
    assert grid.coordinate_crs.to_epsg() == 32654
    assert grid.source_format == "wrg"
    parsed_by_extension = parse_resource_grid(path, "54N")
    assert parsed_by_extension.speeds == pytest.approx(grid.speeds)
    assert parsed_by_extension.coordinate_crs.to_epsg() == 32654


def test_wrg_zone_is_defaulted_and_selectable(tmp_path: Path) -> None:
    path = tmp_path / "wind.wrg"
    make_wrg(path)

    assert parse_resource_grid(path).coordinate_crs.to_epsg() == 32654

    grid = parse_resource_grid(path, "53N")
    assert grid.coordinate_crs.to_epsg() == 32653
    assert parse_wrg(path, "55N").coordinate_crs.to_epsg() == 32655
    assert parse_wrg(path, "54S").coordinate_crs.to_epsg() == 32754
    assert parse_wrg(path, "1N").coordinate_crs.to_epsg() == 32601
    assert parse_wrg(path, "60S").coordinate_crs.to_epsg() == 32760

    with pytest.raises(MascotFormatError, match="1N〜60N"):
        parse_wrg(path, "61N")


def test_parse_wrg_rejects_incomplete_grid(tmp_path: Path) -> None:
    path = tmp_path / "incomplete.wrg"
    path.write_text(
        "2 2 500000 4600000 100\n"
        "GridPoint 500000 4600000 0 100 8 2\n",
        encoding="ascii",
    )

    with pytest.raises(MascotFormatError, match="格子データの数"):
        parse_wrg(path, "54N")


def test_contour_levels_align_to_color_map_minimum_and_division_step() -> None:
    levels = _contour_levels(
        np.array([3.7, 4.1, 5.2, 6.1]),
        interval=0.5,
        anchor=4.0,
    )
    assert levels == pytest.approx([4.0, 4.5, 5.0, 5.5, 6.0])


def test_render_map_preview_returns_png_for_wind_grid(tmp_path: Path) -> None:
    source = tmp_path / "preview.mrg"
    make_mrg(source, [
        "-3000 -3000 100 4 2",
        "-3000 -2975 101 6 2",
        "-2975 -3000 102 8 2",
        "-2975 -2975 103 10 2",
    ])

    image = render_map_preview(
        parse_mrg(source),
        4,
        9,
        10,
        0.5,
        opacity_percent=55,
        show_legend_title=False,
        legend_position="left",
    )

    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert imread(io.BytesIO(image), format="png").shape[0] > 100


def test_create_exports_writes_georeferenced_raster_and_contours(tmp_path: Path) -> None:
    source = tmp_path / "grid.mrg"
    make_mrg(source, [
        "-3000 -3000 100 4 2",
        "-3000 -2975 101 6 2",
        "-2975 -3000 102 8 2",
        "-2975 -2975 103 10 2",
    ])
    grid = parse_mrg(source)
    output = tmp_path / "output"

    create_exports(
        grid,
        output,
        1.0,
        color_minimum=4,
        color_maximum=9,
        color_divisions=10,
    )

    with rasterio.open(output / "wind_speed.tif") as raster:
        assert (raster.width, raster.height) == (2, 2)
        assert raster.crs is not None
        assert raster.nodata is not None
        band = raster.read(1)
        assert band[0, 1] == pytest.approx(10 * math.gamma(1.5))
        assert band[1, 0] == pytest.approx(4 * math.gamma(1.5))
        tags = raster.tags()
        assert tags["wind_color_minimum_m_s"] == "4"
        assert tags["wind_color_maximum_m_s"] == "9"
        assert tags["wind_color_divisions"] == "10"
        assert tags["wind_color_step_m_s"] == "0.5"
        assert tags["kmz_opacity_percent"] == "80"
        west, south, east, north = raster.bounds
        assert (west, south, east, north) == pytest.approx((-12.5, -12.5, 37.5, 37.5))
        to_wgs84 = Transformer.from_crs(raster.crs, CRS.from_epsg(4326), always_xy=True)
        raster_southwest = to_wgs84.transform(0, 0)
    expected_southwest = TransformerGroup(
        CRS.from_epsg(4301),
        CRS.from_epsg(4326),
        always_xy=True,
    ).transformers[0].transform(grid.sw_longitude, grid.sw_latitude)
    assert raster_southwest == pytest.approx(expected_southwest, abs=1e-7)
    contours = json.loads((output / "wind_speed_contours.geojson").read_text(encoding="utf-8"))
    assert contours["type"] == "FeatureCollection"
    assert contours["features"]
    with zipfile.ZipFile(output / "wind_speed.kmz") as kmz:
        assert {
            "doc.kml",
            "wind_speed.png",
            "wind_legend.png",
            "wind_legend_title.png",
        } <= set(kmz.namelist())
        kml = ET.fromstring(kmz.read("doc.kml"))
    namespace = {"kml": "http://www.opengis.net/kml/2.2"}
    draw_order = kml.findtext(".//kml:GroundOverlay/kml:drawOrder", namespaces=namespace)
    assert draw_order == "1"
    assert kml.findtext(".//kml:GroundOverlay/kml:altitudeMode", namespaces=namespace) == "absolute"
    assert kml.findtext(".//kml:GroundOverlay/kml:altitude", namespaces=namespace) == "0"
    assert kml.findtext(".//kml:Style[@id='contour']/kml:LineStyle/kml:color", namespaces=namespace) == "cc202020"
    line_strings = kml.findall(".//kml:LineString", namespace)
    assert line_strings
    for line_string in line_strings:
        assert line_string.findtext("kml:altitudeMode", namespaces=namespace) == "absolute"
        coordinates = line_string.findtext("kml:coordinates", namespaces=namespace)
        assert coordinates
        assert all(point.endswith(",0") for point in coordinates.split())
    legend_overlays = kml.findall(".//kml:ScreenOverlay", namespace)
    assert len(legend_overlays) == 2
    legend_resources = {
        overlay.findtext("kml:Icon/kml:href", namespaces=namespace):
        overlay.findtext("kml:name", namespaces=namespace)
        for overlay in legend_overlays
    }
    assert legend_resources == {
        "wind_legend.png": "平均風速カラーバー（m/s）",
        "wind_legend_title.png": "平均風速凡例タイトル",
    }
    legend_orders = {
        overlay.findtext("kml:Icon/kml:href", namespaces=namespace):
        overlay.findtext("kml:drawOrder", namespaces=namespace)
        for overlay in legend_overlays
    }
    assert legend_orders == {"wind_legend.png": "2", "wind_legend_title.png": "3"}
    qml = ET.parse(output / "wind_speed.qml")
    color_ramp = qml.find(".//colorrampshader")
    assert color_ramp is not None
    assert color_ramp.get("colorRampType") == "DISCRETE"
    items = color_ramp.findall("item")
    assert len(items) == 11
    assert [float(item.get("value")) for item in items] == pytest.approx(
        [4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9]
    )
    assert len({item.get("color") for item in items}) == 10


def test_create_wind_speed_geotiff_writes_unstyled_float_raster(tmp_path: Path) -> None:
    source = tmp_path / "wind.wrg"
    make_wrg(source)
    grid = parse_wrg(source, "54S")
    path = create_wind_speed_geotiff(grid, tmp_path / "exports" / "wind.tif")

    with rasterio.open(path) as raster:
        assert raster.crs.to_epsg() == 32754
        assert (raster.width, raster.height) == (3, 2)
        assert raster.dtypes == ("float32",)
        assert raster.descriptions == ("Weibull mean wind speed (m/s)",)
        assert raster.tags()["source_format"] == "wrg"
        assert "wind_color_minimum_m_s" not in raster.tags()
        assert raster.read(1)[1, 0] == pytest.approx(9.26 * math.gamma(1 + 1 / 1.95))


def test_web_form_returns_downloadable_archive(tmp_path: Path) -> None:
    client = TestClient(app)
    page = client.get("/")
    browser_script = client.get("/static/app.js")
    browser_styles = client.get("/static/app.css")
    assert page.status_code == 200
    assert browser_script.status_code == 200
    assert browser_styles.status_code == 200
    assert 'role="tablist"' in page.text
    assert 'id="colored-panel" role="tabpanel" aria-labelledby="colored-tab"' in page.text
    assert 'id="mean-panel" role="tabpanel" aria-labelledby="mean-tab" hidden' in page.text
    assert 'data-ja="色付きマップ" data-en="Colored map"' in page.text
    assert 'data-ja="WRG → 平均風速" data-en="WRG → Mean wind speed"' in page.text
    assert 'data-ja="WRG → AEP" data-en="WRG → AEP"' in page.text
    assert page.text.count('role="tab"') == 3
    assert 'name="wrg_files" type="file" accept=".wrg" multiple required' in page.text
    assert 'zoneSelect.name = "utm_zones"' in browser_script.text
    assert 'hemisphereSelect.name = "utm_hemispheres"' in browser_script.text
    assert "body: new FormData(event.target)" in browser_script.text
    assert 'endpoint: "/conversion-jobs/mean-wind-speed"' in browser_script.text
    assert "request.send(formData)" in browser_script.text
    assert 'request.upload.addEventListener("progress"' in browser_script.text
    assert 'id="geotiff_file_logs" class="conversion-file-logs"' in page.text
    assert 'id="geotiff_progress" max="100" value="0"' in page.text
    assert 'id="geotiff_status" class="conversion-overall-status" role="status" aria-live="polite"' in page.text
    assert page.text.index('id="geotiff_file_logs"') < page.text.index('id="geotiff_status"')
    assert 'href="/static/app.css"' in page.text
    assert 'src="/static/app.js"' in page.text
    assert "window.WIND_CONFIG" in browser_script.text
    assert ".map-preview" in browser_styles.text
    assert 'data-ja="風況解析GIS変換アプリ" data-en="Wind Resource GIS Converter"' in page.text
    assert "MASCOTから出力される .mrg ファイル" in page.text
    assert "汎用の風況解析シミュレーションで使われる .wrg ファイル" in page.text
    assert 'name="color_minimum"' in page.text
    assert 'name="color_maximum"' in page.text
    assert 'name="color_divisions"' in page.text
    assert 'name="interval_mode" aria-label="コンター間隔の設定方法"' in page.text
    assert '<option value="linked" selected data-ja="連動" data-en="Linked">連動</option>' in page.text
    assert '<option value="manual" data-ja="任意" data-en="Custom">任意</option>' in page.text
    assert 'name="interval" type="number" min="0.1" max="100" step="any" value="0.5" readonly required' in page.text
    assert '<div class="division-contour-setting">' in page.text
    assert "intervalInput.value = formatNumber((maximum - minimum) / divisions)" in browser_script.text
    assert "intervalInput.readOnly = linked" in browser_script.text
    assert 'id="preview_ramp"' in page.text
    assert 'id="preview_summary"' in page.text
    assert 'data-ja-aria="カラーマップのプレビュー" data-en-aria="Color map preview"' in page.text
    assert 'id="map_preview_image"' in page.text
    assert 'data-ja-aria="風速コンター図のプレビュー" data-en-aria="Wind speed contour map preview"' in page.text
    assert 'id="map_preview_status"' in page.text
    assert 'fetch("/preview"' in browser_script.text
    assert '["#show_legend_title", "#legend_position"]' in browser_script.text
    assert 'opacityValue.value = `${opacityInput.value}%`' in browser_script.text
    assert "updateColorPreview" in browser_script.text
    assert "currentLanguage().summary(divisions, formatNumber((maximum - minimum) / divisions))" in browser_script.text
    assert 'name="show_legend_title"' in page.text
    assert 'name="legend_position"' in page.text
    assert 'accept=".mrg,.wrg"' in page.text
    assert 'name="utm_zone" aria-label="UTMゾーン番号"' in page.text
    assert 'name="utm_hemisphere" aria-label="UTM半球"' in page.text
    assert 'id="coordinate_system" class="coordinate-system" hidden' in page.text
    assert 'utmZoneInput.required = isWrg' in browser_script.text
    assert 'utmHemisphereInput.required = isWrg' in browser_script.text
    assert f'<option value="54" selected>54</option>' in page.text
    assert '<option value="60">60</option>' in page.text
    assert '<option value="N" selected>N</option>' in page.text
    assert '<option value="S">S</option>' in page.text
    assert '<label for="language">Language</label>' in page.text
    assert '<select id="language" aria-label="Language">' in page.text
    assert '<option value="ja" selected>日本語</option>' in page.text
    assert '<option value="en">English</option>' in page.text
    assert 'data-en="Wind Resource GIS Converter"' in page.text
    assert '<option value="right" selected data-ja="右" data-en="Right">右</option>' in page.text
    assert '<option value="left" data-ja="左" data-en="Left">左</option>' in page.text
    assert '<option value="true" selected data-ja="タイトルとカラーバーを表示" data-en="Show title and color bar">タイトルとカラーバーを表示</option>' in page.text
    assert '<option value="false" data-ja="カラーバーのみ表示" data-en="Color bar only">カラーバーのみ表示</option>' in page.text
    assert "${timestamp}_mascot_wind_contours.zip" in browser_script.text
    assert "now.getFullYear()" in browser_script.text
    assert 'name="color_minimum" type="number" min="0" step="0.1" value="4"' in page.text
    assert 'name="color_maximum" type="number" min="0.1" step="0.1" value="9"' in page.text
    assert (
        f'name="kmz_opacity_percent" type="range" min="0" max="100" step="1" '
        f'value="{DEFAULT_KMZ_OPACITY_PERCENT}"'
    ) in page.text
    assert f">{DEFAULT_KMZ_OPACITY_PERCENT}%</output>" in page.text
    assert (
        f'name="color_divisions" type="number" min="1" max="{MAX_COLOR_DIVISIONS}" '
        f'step="1" value="{DEFAULT_COLOR_DIVISIONS}"'
    ) in page.text

    source = tmp_path / "grid.mrg"
    make_mrg(source, [
        "-3000 -3000 100 4 2",
        "-3000 -2975 101 6 2",
        "-2975 -3000 102 8 2",
        "-2975 -2975 103 10 2",
    ])

    preview_response = TestClient(app).post(
        "/preview",
        files={"mrg_file": ("grid.mrg", source.read_bytes(), "text/plain")},
        data={
            "interval": "1.0",
            "interval_mode": "linked",
            "color_minimum": "2",
            "color_maximum": "8",
            "color_divisions": "12",
            "kmz_opacity_percent": "55",
            "show_legend_title": "false",
            "legend_position": "left",
            "utm_zone": "54",
            "utm_hemisphere": "N",
        },
    )
    assert preview_response.status_code == 200
    assert preview_response.headers["content-type"] == "image/png"
    assert preview_response.content.startswith(b"\x89PNG\r\n\x1a\n")
    preview_image = imread(io.BytesIO(preview_response.content), format="png")
    assert preview_image.shape[1] > preview_image.shape[0]

    response = TestClient(app).post(
        "/convert",
        files={"mrg_file": ("grid.mrg", source.read_bytes(), "text/plain")},
        data={"interval": "1.0"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "wind_speed.tif" in archive.namelist()
        assert "wind_speed.kmz" in archive.namelist()
        with rasterio.MemoryFile(archive.read("wind_speed.tif")) as memory_file:
            with memory_file.open() as raster:
                assert raster.tags()["wind_color_minimum_m_s"] == "4.0"
                assert raster.tags()["wind_color_maximum_m_s"] == "9.0"
                assert raster.tags()["wind_color_divisions"] == "10"
                assert raster.tags()["kmz_opacity_percent"] == "80"
        default_kmz = zipfile.ZipFile(io.BytesIO(archive.read("wind_speed.kmz")))
        default_kml = ET.fromstring(default_kmz.read("doc.kml"))
        default_legend = imread(
            io.BytesIO(default_kmz.read("wind_legend.png")),
            format="png",
        )
        assert default_legend[:, :, 3].min() == pytest.approx(1.0)
        assert default_legend.shape[0] > default_legend.shape[1]
        assert default_legend.shape[1] / default_legend.shape[0] == pytest.approx(
            0.8 / 4.13,
            abs=0.01,
        )
        bar_sample = default_legend[
            default_legend.shape[0] // 2,
            default_legend.shape[1] // 3,
            :3,
        ]
        assert bar_sample.mean() < 0.9
        title_image = imread(
            io.BytesIO(default_kmz.read("wind_legend_title.png")),
            format="png",
        )
        assert title_image[:, :, 3].min() == pytest.approx(0.0)
        assert title_image[:, :, 3].max() == pytest.approx(1.0)
        kml_namespace = {"k": "http://www.opengis.net/kml/2.2"}
        default_screen_overlays = default_kml.findall(".//k:ScreenOverlay", kml_namespace)
        assert {
            overlay.findtext("k:Icon/k:href", namespaces=kml_namespace)
            for overlay in default_screen_overlays
        } == {"wind_legend.png", "wind_legend_title.png"}
        overlay_positions = {
            overlay.findtext("k:Icon/k:href", namespaces=kml_namespace):
            (
                overlay.find("k:screenXY", kml_namespace).get("x"),
                overlay.find("k:screenXY", kml_namespace).get("y"),
                overlay.find("k:size", kml_namespace).get("x"),
                overlay.find("k:size", kml_namespace).get("y"),
            )
            for overlay in default_screen_overlays
        }
        assert overlay_positions == {
            "wind_legend.png": ("0.78", "0.955", "0.05", "0.55"),
            "wind_legend_title.png": ("0.21", "0.985", "0.32", "0"),
        }
        assert default_kml.findtext(
            ".//{http://www.opengis.net/kml/2.2}Style[@id='contour']/"
            "{http://www.opengis.net/kml/2.2}LineStyle/"
            "{http://www.opengis.net/kml/2.2}color"
        ) == "cc202020"
        default_overlay = imread(io.BytesIO(default_kmz.read("wind_speed.png")), format="png")
        assert float(default_overlay[:, :, 3].max()) == pytest.approx(0.8, abs=0.01)
        default_kmz.close()

    custom_response = TestClient(app).post(
        "/convert",
        files={"mrg_file": ("grid.mrg", source.read_bytes(), "text/plain")},
        data={
            "interval": "1.0",
            "interval_mode": "manual",
            "color_minimum": "2",
            "color_maximum": "8",
            "color_divisions": "12",
            "kmz_opacity_percent": "55",
            "show_legend_title": "false",
            "legend_position": "left",
        },
    )
    assert custom_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(custom_response.content)) as archive:
        with rasterio.MemoryFile(archive.read("wind_speed.tif")) as memory_file:
            with memory_file.open() as raster:
                assert raster.tags()["wind_color_minimum_m_s"] == "2.0"
                assert raster.tags()["wind_color_maximum_m_s"] == "8.0"
                assert raster.tags()["wind_color_divisions"] == "12"
                assert raster.tags()["kmz_opacity_percent"] == "55"
        contours = json.loads(archive.read("wind_speed_contours.geojson"))
        contour_values = {
            feature["properties"]["wind_speed_m_s"]
            for feature in contours["features"]
        }
        assert contour_values
        assert all((value - 2) % 1 == pytest.approx(0) for value in contour_values)
        custom_kmz = zipfile.ZipFile(io.BytesIO(archive.read("wind_speed.kmz")))
        custom_kml = ET.fromstring(custom_kmz.read("doc.kml"))
        custom_legend = imread(
            io.BytesIO(custom_kmz.read("wind_legend.png")),
            format="png",
        )
        assert custom_legend[:, :, 3].min() == pytest.approx(1.0)
        custom_bar_sample = custom_legend[
            custom_legend.shape[0] // 2,
            custom_legend.shape[1] // 3,
            :3,
        ]
        assert custom_bar_sample.mean() > bar_sample.mean()
        custom_screen_overlays = custom_kml.findall(".//k:ScreenOverlay", kml_namespace)
        assert len(custom_screen_overlays) == 1
        assert custom_screen_overlays[0].findtext(
            "k:Icon/k:href",
            namespaces=kml_namespace,
        ) == "wind_legend.png"
        assert custom_screen_overlays[0].find("k:overlayXY", kml_namespace).get("x") == "1"
        assert custom_screen_overlays[0].find("k:screenXY", kml_namespace).get("x") == "0.213"
        assert "wind_legend_title.png" not in custom_kmz.namelist()
        custom_line_color = custom_kml.findtext(
            ".//{http://www.opengis.net/kml/2.2}Style[@id='contour']/"
            "{http://www.opengis.net/kml/2.2}LineStyle/"
            "{http://www.opengis.net/kml/2.2}color"
        )
        assert custom_line_color == "8c202020"
        custom_overlay = imread(io.BytesIO(custom_kmz.read("wind_speed.png")), format="png")
        assert float(custom_overlay[:, :, 3].max()) == pytest.approx(0.55, abs=0.01)
        custom_kmz.close()


def test_web_form_rejects_invalid_color_scale(tmp_path: Path) -> None:
    source = tmp_path / "grid.mrg"
    make_mrg(source, [
        "-3000 -3000 100 4 2",
        "-3000 -2975 101 6 2",
        "-2975 -3000 102 8 2",
        "-2975 -2975 103 10 2",
    ])

    response = TestClient(app).post(
        "/convert",
        files={"mrg_file": ("grid.mrg", source.read_bytes(), "text/plain")},
        data={
            "interval": "1.0",
            "color_minimum": "9",
            "color_maximum": "4",
            "color_divisions": "10",
        },
    )

    assert response.status_code == 400
    assert "上限は下限より大きい" in response.json()["detail"]


def test_web_form_previews_and_exports_wrg_input(tmp_path: Path) -> None:
    source = tmp_path / "wind.wrg"
    make_wrg(source)
    client = TestClient(app)
    data = {
        "interval": "0.1",
        "interval_mode": "manual",
        "color_minimum": "9.1",
        "color_maximum": "9.4",
        "color_divisions": "3",
        "utm_zone": "54",
        "utm_hemisphere": "N",
    }
    files = {"mrg_file": ("wind.wrg", source.read_bytes(), "text/plain")}

    preview_response = client.post("/preview", files=files, data=data)
    assert preview_response.status_code == 200
    assert preview_response.headers["content-type"] == "image/png"
    assert preview_response.content.startswith(b"\x89PNG\r\n\x1a\n")

    response = client.post("/convert", files=files, data=data)
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        with rasterio.MemoryFile(archive.read("wind_speed.tif")) as memory_file:
            with memory_file.open() as raster:
                assert raster.crs.to_epsg() == 32654
                assert raster.bounds.left == pytest.approx(403027.909)
                assert raster.bounds.top == pytest.approx(4696436.109)
                assert raster.tags()["source_format"] == "wrg"
                assert raster.tags()["source_horizontal_datum"] == (
                    "WGS 84 / UTM zone 54N (EPSG:32654)"
                )
        contours = json.loads(archive.read("wind_speed_contours.geojson"))
        assert contours["features"]
        longitude, latitude = contours["features"][0]["geometry"]["coordinates"][0]
        assert 139 < longitude < 142
        assert 41 < latitude < 44

    other_zone_data = {**data, "utm_zone": "53"}
    other_zone_response = client.post("/convert", files=files, data=other_zone_data)
    assert other_zone_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(other_zone_response.content)) as archive:
        with rasterio.MemoryFile(archive.read("wind_speed.tif")) as memory_file:
            with memory_file.open() as raster:
                assert raster.crs.to_epsg() == 32653

    other_hemisphere_data = {**data, "utm_hemisphere": "S"}
    other_hemisphere_response = client.post("/convert", files=files, data=other_hemisphere_data)
    assert other_hemisphere_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(other_hemisphere_response.content)) as archive:
        with rasterio.MemoryFile(archive.read("wind_speed.tif")) as memory_file:
            with memory_file.open() as raster:
                assert raster.crs.to_epsg() == 32754

    invalid_zone_response = client.post(
        "/convert",
        files=files,
        data={**data, "utm_zone": "61"},
    )
    assert invalid_zone_response.status_code == 400
    assert "1〜60" in invalid_zone_response.json()["detail"]

    default_zone_response = client.post(
        "/convert",
        files=files,
        data={
            key: value
            for key, value in data.items()
            if key not in {"utm_zone", "utm_hemisphere"}
        },
    )
    assert default_zone_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(default_zone_response.content)) as archive:
        with rasterio.MemoryFile(archive.read("wind_speed.tif")) as memory_file:
            with memory_file.open() as raster:
                assert raster.crs.to_epsg() == 32654


def test_web_form_exports_one_geotiff_per_wrg_with_individual_crs(tmp_path: Path) -> None:
    source = tmp_path / "sample.wrg"
    make_wrg(source)
    content = source.read_bytes()
    response = TestClient(app).post(
        "/convert-wrg-geotiffs",
        files=[
            ("wrg_files", ("north.wrg", content, "text/plain")),
            ("wrg_files", ("south.wrg", content, "text/plain")),
        ],
        data={"utm_zones": ["54", "54"], "utm_hemispheres": ["N", "S"]},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["north.tif", "south.tif"]
        for name, epsg in (("north.tif", 32654), ("south.tif", 32754)):
            with rasterio.MemoryFile(archive.read(name)) as memory_file:
                with memory_file.open() as raster:
                    assert raster.crs.to_epsg() == epsg
                    assert raster.dtypes == ("float32",)
                    assert "wind_color_minimum_m_s" not in raster.tags()


def test_web_form_disambiguates_duplicate_geotiff_names(tmp_path: Path) -> None:
    source = tmp_path / "wind.wrg"
    make_wrg(source)
    response = TestClient(app).post(
        "/convert-wrg-geotiffs",
        files=[
            ("wrg_files", ("wind.wrg", source.read_bytes(), "text/plain")),
            ("wrg_files", ("wind.wrg", source.read_bytes(), "text/plain")),
        ],
        data={"utm_zones": ["54", "54"], "utm_hemispheres": ["N", "N"]},
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["wind.tif", "wind_2.tif"]


def test_web_form_rejects_non_wrg_for_geotiff_export(tmp_path: Path) -> None:
    source = tmp_path / "grid.mrg"
    make_mrg(source, [
        "-3000 -3000 100 4 2",
        "-3000 -2975 101 6 2",
        "-2975 -3000 102 8 2",
        "-2975 -2975 103 10 2",
    ])
    response = TestClient(app).post(
        "/convert-wrg-geotiffs",
        files=[("wrg_files", ("grid.mrg", source.read_bytes(), "text/plain"))],
        data={"utm_zones": ["54"], "utm_hemispheres": ["N"]},
    )

    assert response.status_code == 400
    assert ".wrg" in response.json()["detail"]


def test_web_form_requires_valid_utm_settings_for_each_wrg(tmp_path: Path) -> None:
    source = tmp_path / "wind.wrg"
    make_wrg(source)
    content = source.read_bytes()
    files = [
        ("wrg_files", ("first.wrg", content, "text/plain")),
        ("wrg_files", ("second.wrg", content, "text/plain")),
    ]

    mismatched_settings = TestClient(app).post(
        "/convert-wrg-geotiffs",
        files=files,
        data={"utm_zones": ["54"], "utm_hemispheres": ["N", "S"]},
    )
    assert mismatched_settings.status_code == 400

    invalid_zone = TestClient(app).post(
        "/convert-wrg-geotiffs",
        files=files,
        data={"utm_zones": ["54", "61"], "utm_hemispheres": ["N", "S"]},
    )
    assert invalid_zone.status_code == 400
    assert "UTM" in invalid_zone.json()["detail"]


def test_web_form_rejects_unsupported_file_extension() -> None:
    response = TestClient(app).post(
        "/convert",
        files={"mrg_file": ("grid.txt", b"not a MASCOT grid", "text/plain")},
    )

    assert response.status_code == 400
    assert ".mrgまたは.wrg" in response.json()["detail"]


@pytest.mark.parametrize("sector_count", [7, 12, 16])
def test_parse_wrg_preserves_arbitrary_number_of_sector_distributions(
    tmp_path: Path,
    sector_count: int,
) -> None:
    frequencies = [1000 // sector_count] * sector_count
    frequencies[-1] += 1000 - sum(frequencies)
    path = tmp_path / f"sectors_{sector_count}.wrg"
    make_directional_wrg(path, [(frequency, 100, 200) for frequency in frequencies])

    grid = parse_wrg(path, "54N")

    assert grid.sector_frequencies is not None
    assert grid.sector_scales is not None
    assert grid.sector_shapes is not None
    assert grid.sector_frequencies.shape == (2, 2, sector_count)
    assert grid.sector_frequencies[0, 0].sum() == pytest.approx(100)
    assert np.all(grid.sector_scales == 10)
    assert np.all(grid.sector_shapes == 2)


def test_annual_energy_uses_sector_frequency_linear_curve_and_zero_outside_range(
    tmp_path: Path,
) -> None:
    path = tmp_path / "directional.wrg"
    make_directional_wrg(path, [(250, 50, 100), (750, 150, 100)])
    grid = parse_wrg(path, "54N")
    curve_speeds, curve_powers = parse_power_curve(b"wind speed,power\n0,0\n20,1000\n")

    annual_energy = calculate_annual_energy(grid, curve_speeds, curve_powers)

    edges = np.append(np.arange(0, 20, 0.5), 20)
    midpoints = (edges[:-1] + edges[1:]) / 2
    expected_mean_power_5 = np.sum(
        50 * midpoints * (np.exp(-edges[:-1] / 5) - np.exp(-edges[1:] / 5))
    )
    expected_mean_power_15 = np.sum(
        50 * midpoints * (np.exp(-edges[:-1] / 15) - np.exp(-edges[1:] / 15))
    )
    expected = (0.25 * expected_mean_power_5 + 0.75 * expected_mean_power_15) * 8760 / 1000
    progress: list[int] = []
    annual_energy = calculate_annual_energy(grid, curve_speeds, curve_powers, progress.append)
    assert annual_energy == pytest.approx(np.full((2, 2), expected), rel=1e-6)
    assert progress[-1] == 100
    assert progress == sorted(progress)
    parallel_energy = calculate_annual_energy(
        grid,
        curve_speeds,
        curve_powers,
        workers=2,
    )
    assert parallel_energy == pytest.approx(annual_energy, rel=1e-6)
    grid.speeds.fill(np.nan)
    assert calculate_annual_energy(grid, curve_speeds, curve_powers) == pytest.approx(
        np.full((2, 2), expected),
        rel=1e-6,
    )


@pytest.mark.parametrize(
    ("content", "expected_speeds", "expected_powers"),
    [
        (b"Wind speed,Power\n10,500\n0,0\n", [0, 10], [0, 500]),
        (b"0;0\n5;250\n10;1000\n", [0, 5, 10], [0, 250, 1000]),
        (b"0\t0\n4\t400\n", [0, 4], [0, 400]),
    ],
)
def test_parse_power_curve_delimiters_headers_and_unsorted_points(
    content: bytes,
    expected_speeds: list[float],
    expected_powers: list[float],
) -> None:
    speeds, powers = parse_power_curve(content)

    assert speeds.tolist() == expected_speeds
    assert powers.tolist() == expected_powers


@pytest.mark.parametrize(
    "content",
    [
        b"0,0\n0,100\n",
        b"0,-1\n10,100\n",
        b"0,0\n",
        b"wind,power\nnot-a-number,100\n",
    ],
)
def test_parse_power_curve_rejects_invalid_values(content: bytes) -> None:
    with pytest.raises(MascotFormatError):
        parse_power_curve(content)


def test_web_power_curve_preview_and_annual_energy_zip(tmp_path: Path) -> None:
    path = tmp_path / "directional.wrg"
    make_directional_wrg(path, [(500, 100, 200), (500, 100, 200)])
    content = path.read_bytes()
    curve = b"Wind speed,Power kW\n0,1000\n100,1000\n"
    client = TestClient(app)

    preview = client.post(
        "/preview-power-curve",
        files={"power_curve_file": ("curve.csv", curve, "text/csv")},
    )
    assert preview.status_code == 200
    assert len(preview.json()["points"]) == 2

    response = client.post(
        "/convert-wrg-energy-geotiffs",
        files=[
            ("wrg_files", ("north.wrg", content, "text/plain")),
            ("wrg_files", ("south.wrg", content, "text/plain")),
            ("power_curve_files", ("turbine_a.csv", curve, "text/csv")),
            ("power_curve_files", ("turbine_b.csv", b"0,500\n100,500\n", "text/csv")),
        ],
        data={
            "utm_zones": ["54", "54"],
            "utm_hemispheres": ["N", "S"],
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == [
            "north_turbine_a.tif",
            "north_turbine_b.tif",
            "south_turbine_a.tif",
            "south_turbine_b.tif",
        ]
        for name, epsg, expected_energy in (
            ("north_turbine_a.tif", 32654, 8760),
            ("north_turbine_b.tif", 32654, 4380),
            ("south_turbine_a.tif", 32754, 8760),
            ("south_turbine_b.tif", 32754, 4380),
        ):
            with rasterio.MemoryFile(archive.read(name)) as memory_file:
                with memory_file.open() as raster:
                    assert raster.crs.to_epsg() == epsg
                    assert raster.dtypes == ("float32",)
                    assert raster.descriptions == ("Gross annual energy production (MWh/year)",)
                    assert raster.tags()["unit"] == "MWh/year"
                    assert raster.tags()["assumptions"] == "No availability, electrical, or wake losses"
                    assert np.all(raster.read(1) == pytest.approx(expected_energy))


@pytest.mark.parametrize(
    ("mode", "endpoint"),
    [
        ("mean", "/conversion-jobs/mean-wind-speed"),
        ("energy", "/conversion-jobs/annual-energy"),
    ],
)
def test_conversion_job_reports_per_file_progress_and_downloads_zip(
    tmp_path: Path,
    mode: str,
    endpoint: str,
) -> None:
    path = tmp_path / "directional.wrg"
    make_directional_wrg(path, [(500, 100, 200), (500, 100, 200)])
    wrg_content = path.read_bytes()
    files = [
        ("wrg_files", ("north.wrg", wrg_content, "text/plain")),
        ("wrg_files", ("south.wrg", wrg_content, "text/plain")),
    ]
    if mode == "energy":
        files.extend([
            ("power_curve_files", ("turbine-a.csv", b"0,0\n20,2000\n", "text/csv")),
            ("power_curve_files", ("turbine-b.csv", b"0,0\n20,1000\n", "text/csv")),
        ])
    client = TestClient(app)

    started = client.post(
        endpoint,
        files=files,
        data={"utm_zones": ["54", "54"], "utm_hemispheres": ["N", "S"]},
    )

    assert started.status_code == 202
    job_id = started.json()["id"]
    for _ in range(200):
        status = client.get(f"/conversion-jobs/{job_id}")
        assert status.status_code == 200
        if status.json()["status"] in {"complete", "failed"}:
            break
        time.sleep(0.01)
    assert status.json()["status"] == "complete"
    assert status.json()["progress"] == 100
    expected_names = (
        ["north.wrg", "south.wrg"]
        if mode == "mean"
        else [
            "north.wrg × turbine-a.csv",
            "north.wrg × turbine-b.csv",
            "south.wrg × turbine-a.csv",
            "south.wrg × turbine-b.csv",
        ]
    )
    assert [item["name"] for item in status.json()["files"]] == expected_names
    assert all(
        item["stage"] == "complete" and item["progress"] == 100
        for item in status.json()["files"]
    )

    downloaded = client.get(f"/conversion-jobs/{job_id}/download")

    assert downloaded.status_code == 200
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        expected_archive_names = (
            ["north.tif", "south.tif"]
            if mode == "mean"
            else [
                "north_turbine-a.tif",
                "north_turbine-b.tif",
                "south_turbine-a.tif",
                "south_turbine-b.tif",
            ]
        )
        assert archive.namelist() == expected_archive_names


def test_conversion_job_progress_weights_upload_analysis_and_zip() -> None:
    job_id = "progress-weight-test"
    with _conversion_jobs_lock:
        _conversion_jobs[job_id] = {
            "status": "running",
            "stage": "analysis",
            "files": [{"name": "sample.wrg", "stage": "parsing", "progress": 50}],
            "archive_progress": 0,
        }
    try:
        assert _public_job_status(job_id)["progress"] == 50
        with _conversion_jobs_lock:
            _conversion_jobs[job_id].update(status="packaging", stage="packaging")
            _conversion_jobs[job_id]["archive_progress"] = 50
        status = _public_job_status(job_id)
        assert status["stage"] == "packaging"
        assert status["progress"] == 95
        with _conversion_jobs_lock:
            _conversion_jobs[job_id]["status"] = "complete"
        assert _public_job_status(job_id)["progress"] == 100
    finally:
        with _conversion_jobs_lock:
            _conversion_jobs.pop(job_id, None)


def test_energy_ui_includes_curve_preview_and_conversion_progress() -> None:
    client = TestClient(app)
    page = client.get("/")
    script = client.get("/static/app.js")
    energy_script = client.get("/static/energy.js")

    assert page.status_code == 200
    assert 'id="energy-panel" role="tabpanel"' in page.text
    assert 'id="power_curve_previews"' in page.text
    assert 'name="power_curve_files" type="file" accept=".csv,text/csv" multiple required' in page.text
    assert 'id="energy_progress" max="100" value="0"' in page.text
    assert 'src="/static/energy.js"' in page.text
    assert script.status_code == 200
    assert energy_script.status_code == 200
    assert 'endpoint: "/conversion-jobs/annual-energy"' in energy_script.text
    assert 'legend.className = "power-curve-legend"' in energy_script.text
    assert "137.508" in energy_script.text
    assert 'id="energy_file_logs" class="conversion-file-logs"' in page.text
    assert page.text.index('id="energy_file_logs"') < page.text.index('id="energy_status"')
    assert "linearly interpolated" in page.text
    assert "0.5 m/s wind-speed intervals" in page.text
