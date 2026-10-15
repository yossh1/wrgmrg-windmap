# Wind Resource GIS Converter

[English](#wind-resource-gis-converter) | [日本語](#風況解析gis変換アプリ)

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

---

# 風況解析GIS変換アプリ

風況解析データから平均風速を計算し、Google Earth ProやQGISで使える地図データを作成するWebアプリです。

## 対応ファイル

- **`.mrg`** — MASCOTから出力されるリソースグリッドファイルです。格子ごとのワイブルパラメーターと位置情報を読み取ります。
- **`.wrg`** — 汎用の風況解析シミュレーションで使われるグリッド形式のファイルです。格子ごとのワイブルパラメーターとUTM座標を読み取ります。アップロード後にUTM zone 1〜60と北半球（N）・南半球（S）を選択してください。初期値は54Nです。UTMの適用範囲（南緯80°〜北緯84°）内で利用できます。

どちらの形式も、各格子の全方位ワイブルパラメーターから平均風速を計算し、GISデータに変換します。

## 計算

各格子の全方位ワイブル尺度 `A` と形状 `k` から、ワイブル分布の平均値を次の式で計算します。

```text
平均風速 [m/s] = A × Γ(1 + 1/k)
```

`.mrg` ではヘッダーに含まれる格子数・間隔・南西端の日本測地系緯度経度を使います。`.wrg` では1行目の格子数・南西端UTM座標・格子間隔と各`GridPoint`の全方位ワイブル尺度A・形状kを使います。

`.mrg` の南西端の緯度・経度は日本測地系（Tokyo Datum、EPSG:4301）として読み込み、PROJの座標変換を使ってWGS 84（EPSG:4326）に変換します。MASCOTのX/Y格子間隔はメートル単位で扱い、変換後の南西端を原点とする局所方位等距離図法（AEQD）に配置します。`.wrg` は選択したUTM zone 1〜60と半球に対応するWGS 84 / UTM座標系を使用します（北半球 EPSG:32601〜32660、南半球 EPSG:32701〜32760）。`.wrg`に測地系の識別情報がないため、WGS 84を前提にします。KMZとGeoJSONはどちらの形式もWGS 84で出力します。

旧日本測地系からWGS 84への変換には、使用するPROJデータベースの変換方法に応じた誤差が残ります。GeoTIFFのメタデータには採用された変換方法と精度が記録されます。MASCOTのX/Y投影法そのものは入力情報から特定できないため、広域または測量精度が必要な用途では、出力位置を既知地点と照合してください。

## 起動方法（Linux / Docker）

### 1. アプリを起動

プロジェクトフォルダーで次を実行します。

```sh
docker compose up --build
```

### 2. ブラウザーで変換

`http://localhost:8000` を開き、入力ファイルと各設定を指定して「変換してZIPをダウンロード」を押します。変換後のZIPには、Google Earth Pro・QGIS用のファイルが含まれます。

#### 入力ファイル

- `.mrg` または `.wrg` を選択します。拡張子に応じて読み取り方法を切り替えます。
- `.wrg` の場合は、ファイル選択後に表示される **UTM zone（1〜60）と半球（N / S）** から座標系を選択してください。初期値は **54N** です。UTMの適用範囲は南緯80°〜北緯84°です。

#### 風速カラーマップとプレビュー

- **下限・上限・分割数**で色分けの範囲と段階を設定します。
- 入力ファイルを選択すると、実際の格子データを使ったコンター図が表示されます。色範囲やコンター間隔などを変更するとプレビューも更新されます。
- カラーマップの色段階、数値範囲、刻み幅のプレビューも設定に合わせて更新されます。
- 範囲外の風速値は、下限色または上限色で表示します。
- 初期値は **4〜9 m/s・10分割** です。分割数は **1〜100** で指定できます。

#### コンター間隔

- 分割数の横にある設定で、**連動**または**任意**を選びます。
- 初期設定の「連動」では、コンター間隔をカラーマップ1段分の幅に合わせます。初期値は **0.5 m/s** です。
- 「任意」にすると、コンター間隔を個別に入力できます。

#### KMZの表示設定

- **不透明度**：色塗り、コンター線、凡例カラーバーの色面に適用します。初期値は **80%**（20%透過）です。カラーバーの背景と数値は読みやすいよう不透明です。
- **凡例タイトル**：「タイトルとカラーバーを表示」または「カラーバーのみ表示」を選びます。
- **カラーバー位置**：マップの右または左を選びます。初期値は右です。左側に置く場合も、マップとの間に隙間を設けて重ならないようにします。
- 凡例タイトルとカラーバーは、Google Earth Pro上で個別に表示・非表示を切り替えられます。

ZIPのファイル名には、ダウンロードしたPCの年月日と時刻（`YYYYMMDD_HHMMSS`）が先頭に付きます（例：`YYYYMMDD_HHMMSS_mascot_wind_contours.zip`）。アップロードした入力ファイルは変換後に削除され、アプリには保存されません。

## テスト

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## ライセンス

このプロジェクトは [MIT License](./LICENSE) のもとで公開しています。

## 出力ファイル

ダウンロードしたZIPを展開してください。

- `wind_speed.kmz` — Google Earth Proで開くと、指定した分割数で色分けした平均風速の色塗り（GroundOverlay、描画順序1）、海抜0 mに固定したコンター線、ブラウザーで指定した側（既定は右）に表示する縦型カラーバー（ScreenOverlay、描画順序2）が表示されます。カラーバーは横幅を抑え、高さを前回の約3分の2にし、マップ端との間隔を詰めてもカラーマップに重ならない位置に配置します。目盛りの数値が切れないよう、画像内のラベル余白を確保します。凡例タイトルは別のScreenOverlay（描画順序3）で、背景透過にしてカラーマップ左上から始まるよう配置し、ブラウザーから表示を省略できます。KMZ内でもタイトルとカラーバーを個別に切り替えられます。凡例には指定したカラーマップ範囲と分割値が表示されます。指定した不透明度は色塗り・コンター線・カラーバーの色面に適用します。カラーバーの背景は白く不透明で、文字も不透明です。色塗り画像とコンター線はどちらも海抜0 m（KML `absolute`）です。
- `wind_speed.tif` — QGISで開くGeoTIFF（単位m/s、位置情報付き）。
- `wind_speed.qml` — 指定した下限・上限・分割数を反映したGeoTIFF用の段階風速カラースタイル。QGISが自動適用しない場合はレイヤーの「スタイル」から読み込みます。
- `wind_speed_contours.geojson` — QGISで読み込めるWGS84のコンター線。属性 `wind_speed_m_s` が風速値です。

## 注意

- 有効なA・k（両方とも正数）の格子のみ風速値を計算します。
- `.mrg`の入力緯度経度は日本測地系（Tokyo Datum）として扱います。`.wrg`ではUTM zone 1〜60と半球（N / S）を選択します。`.wrg`の測地系はWGS 84を前提とします。ファイルと異なる測地系やUTM zoneを選択すると位置がずれるため、既知地点と照合してください。
- `.mrg`由来のGeoTIFFはWGS 84を基準にした局所AEQD座標系、`.wrg`由来のGeoTIFFは選択されたUTM zoneと半球に対応するWGS 84座標系を使用します。日本測地系からWGS 84への変換は近似変換であり、MASCOTのX/Y投影法も入力ファイルからは特定できません。
- KMZの色塗り画像とコンター線は海抜0 mに配置します。標高が0 mより高い陸地では地形の下になるため、Google Earth Proの地形表示によって隠れる場合があります。
- 入力ファイルの内容は処理後に削除されます。

## コード構成

- `app/main.py` — FastAPIの画面・変換APIとリクエスト処理
- `app/grid.py` — MRG/WRGの読み込みと座標系の処理
- `app/visualization.py` — 風速カラーマップ、コンター線、プレビュー描画
- `app/exports.py` — GeoTIFF・QML・GeoJSON・KMZの生成
- `app/settings.py` — アプリの初期設定
- `app/converter.py` — 各モジュールをまとめた変換API
- `app/templates/index.html`、`app/static/` — ブラウザー画面・スタイル・スクリプト
