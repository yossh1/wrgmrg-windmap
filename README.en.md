# Wind Resource GIS Converter

[日本語](./README.md#風況解析gis変換アプリ)

A web application that calculates mean wind speed from wind resource data and creates GIS files for Google Earth Pro and QGIS.

## Supported files

- **`.mrg`** — A resource-grid file exported by MASCOT. It contains grid locations and the Weibull parameters for each grid point.
- **`.wrg`** — A grid file used by general-purpose wind-resource simulation software. It contains UTM coordinates and Weibull parameters for each grid point. Select the UTM zone and hemisphere after uploading. The default is **54N**. UTM is valid between 80°S and 84°N.

For both formats, the application calculates mean wind speed from the all-direction Weibull scale `A` and shape `k` at each grid point:

```text
Mean wind speed [m/s] = A × Γ(1 + 1/k)
```

## Coordinate systems

For `.mrg`, the southwest latitude and longitude are interpreted as Tokyo Datum (EPSG:4301), transformed to WGS 84 (EPSG:4326), and used to create a local azimuthal equidistant (AEQD) grid.

For `.wrg`, select a WGS 84 / UTM zone from **1N through 60N** or **1S through 60S**. The default is **54N**. The GeoTIFF uses the selected UTM CRS (EPSG:32601–32660 in the northern hemisphere, EPSG:32701–32760 in the southern hemisphere). Since WRG files do not identify their geodetic datum, WGS 84 is assumed.

KMZ and GeoJSON files use WGS 84 coordinates.

Transformations from Tokyo Datum may have residual errors depending on the PROJ database and available transformation grids. The exact projection used to create MASCOT's `.mrg` X/Y coordinates cannot be inferred from the file alone. Check output locations against known points when accurate positioning is important.

## Run with Linux / Docker

### 1. Start the application

Run this command from the project directory:

```sh
docker compose up --build
```

### 2. Convert a file

Open `http://localhost:8000`, select an input file and configure the settings, then click **Convert and download ZIP**.

#### Input file

- Select an `.mrg` or `.wrg` file. The application chooses the parser based on the file extension.
- For `.wrg`, select the UTM zone (**1–60**) and hemisphere (**N / S**) shown after choosing the file. The default is **54N**.

#### Color map and preview

- Set the color range with **Minimum**, **Maximum**, and **Number of divisions**.
- After selecting an input file, the app displays a contour-map preview generated from the actual grid data. The preview updates when the color range or contour interval changes.
- A separate color-ramp preview shows the colors, value range, and step size.
- Values outside the selected color range use the minimum or maximum color.
- Defaults: **4–9 m/s**, **10 divisions**. The number of divisions can be set from **1 to 100**.

#### Contour interval

- Choose **Linked** or **Custom** next to the number of color divisions.
- **Linked** (default) sets the contour interval to one color division. The initial interval is **0.5 m/s**.
- **Custom** allows you to enter an independent contour interval.

#### KMZ display settings

- **Opacity** applies to the wind-speed overlay, contour lines, and color area of the legend bar. The default is **80%** (20% transparent). The legend background and labels remain opaque for readability.
- **Legend title**: show both the title and color bar, or show the color bar only.
- **Color-bar position**: left or right of the map. The default is right. The left-side bar is positioned with a gap so it does not overlap the map.
- The legend title and color bar can also be toggled independently in Google Earth Pro.

The downloaded ZIP filename starts with the download computer's local date and time (`YYYYMMDD_HHMMSS`), for example `YYYYMMDD_HHMMSS_mascot_wind_contours.zip`. Uploaded files are deleted after processing and are not retained by the application.

### WRG → GeoTIFF tab

- Select one or more `.wrg` files. Choose the UTM zone number and hemisphere for each file (default: **54N**).
- Each file is converted independently into one single-band Float32 GeoTIFF containing mean wind speed in m/s. No color style is applied, so you can style each raster in QGIS.
- Download the GeoTIFF files together in a ZIP. Output names are based on the input filenames; duplicate names receive a numeric suffix.
- Each GeoTIFF uses the WGS 84 / UTM CRS selected for its WRG file.

## Output files

Extract the downloaded ZIP:

- `wind_speed.kmz` — Open in Google Earth Pro to view the discrete mean-wind-speed overlay, contour lines at altitude 0 m, and the configurable vertical color bar. The legend title and bar are separate screen overlays. The selected opacity applies to the wind overlay, contour lines, and color area of the bar.
- `wind_speed.tif` — Georeferenced GeoTIFF in m/s for QGIS.
- `wind_speed.qml` — Discrete color style for the GeoTIFF. If QGIS does not load it automatically, import it from the layer's **Styles** menu.
- `wind_speed_contours.geojson` — WGS 84 contour lines for QGIS. The `wind_speed_m_s` property contains the contour value.

The KMZ overlay and contour lines are placed at altitude 0 m (KML `absolute`). Terrain in Google Earth Pro may obscure them over land above sea level.

## Project structure

- `app/main.py` — FastAPI routes and request handling.
- `app/grid.py` — MRG/WRG parsing and coordinate reference handling.
- `app/visualization.py` — Wind-speed palettes, contour lines, and map preview.
- `app/exports.py` — GeoTIFF, QML, GeoJSON, and KMZ generation.
- `app/settings.py` — Application defaults.
- `app/converter.py` — Public conversion API that combines the focused modules.
- `app/templates/index.html` and `app/static/` — Browser interface, styles, and scripts.

## Tests

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## License

This project is distributed under the [MIT License](./LICENSE).
