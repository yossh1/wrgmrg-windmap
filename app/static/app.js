const { maxColorDivisions, colorPalettes } = window.WIND_CONFIG;
const translations = {
  ja: {
    invalidColorRange: "下限・上限・分割数を確認してください。",
    missingWrgCrs: "WRGのプレビューにはUTM zone番号と半球を選択してください。",
    missingFile: "ファイルを選択すると、風速コンター図を表示します。",
    invalidSettings: "プレビューする設定値を確認してください。",
    rendering: "風速コンター図を作成中...",
    previewFailed: "プレビューを作成できませんでした。",
    converting: "変換中...",
    convert: "変換してZIPをダウンロード",
    geotiffConverting: "GeoTIFFを作成中...",
    geotiffDownload: "GeoTIFFをZIPでダウンロード",
    zoneNumber: "UTM zone番号",
    hemisphere: "半球",
    geotiffReady: (count) => `${count}個のWRGファイルを個別のGeoTIFFにします。`,
    geotiffUploading: (count, percent) => `${count}個のファイルを送信中... ${percent}%`,
    geotiffProcessing: (count, elapsed) => `${count}個のファイルを変換中です。経過時間: ${elapsed}秒`,
    geotiffComplete: (count) => `${count}個のGeoTIFFをZIPでダウンロードしました。`,
    geotiffError: "GeoTIFFを作成できませんでした。",
    previewSuffix: "の風速コンター図",
    summary: (divisions, interval) => `${divisions}分割・${interval} m/s刻み`,
  },
  en: {
    invalidColorRange: "Check the minimum, maximum, and number of divisions.",
    missingWrgCrs: "Select a UTM zone number and hemisphere to preview a WRG file.",
    missingFile: "Select a file to preview its wind speed contour map.",
    invalidSettings: "Check the settings before previewing.",
    rendering: "Creating wind speed contour map...",
    previewFailed: "Could not create the preview.",
    converting: "Converting...",
    convert: "Convert and download ZIP",
    geotiffConverting: "Creating GeoTIFFs...",
    geotiffDownload: "Download GeoTIFFs as ZIP",
    zoneNumber: "UTM zone number",
    hemisphere: "Hemisphere",
    geotiffReady: (count) => `A separate GeoTIFF will be created for each of the ${count} WRG files.`,
    geotiffUploading: (count, percent) => `Uploading ${count} files... ${percent}%`,
    geotiffProcessing: (count, elapsed) => `Converting ${count} files. Elapsed: ${elapsed}s`,
    geotiffComplete: (count) => `Downloaded a ZIP containing ${count} GeoTIFFs.`,
    geotiffError: "Could not create the GeoTIFFs.",
    previewSuffix: " wind speed contour map",
    summary: (divisions, interval) => `${divisions} divisions · ${interval} m/s interval`,
  },
};
const languageInput = document.querySelector("#language");
const currentLanguage = () => translations[languageInput.value];
let geotiffProgressState = null;
const updateGeotiffStatus = () => {
  if (!geotiffProgressState) return;
  const { phase, count, startedAt, percent = 0 } = geotiffProgressState;
  const progress = document.querySelector("#geotiff_progress");
  const status = document.querySelector("#geotiff_status");
  if (phase === "uploading") {
    progress.value = percent;
    status.textContent = currentLanguage().geotiffUploading(count, percent);
  } else if (phase === "processing") {
    progress.removeAttribute("value");
    const elapsed = Math.floor((Date.now() - startedAt) / 1000);
    status.textContent = currentLanguage().geotiffProcessing(count, elapsed);
  } else if (phase === "complete") {
    progress.value = 100;
    status.textContent = currentLanguage().geotiffComplete(count);
  }
};
const applyLanguage = () => {
  const language = languageInput.value;
  document.documentElement.lang = language;
  document.querySelectorAll("[data-ja][data-en]").forEach((element) => {
    element.textContent = element.dataset[language];
  });
  document.querySelectorAll("[data-ja-aria][data-en-aria]").forEach((element) => {
    element.setAttribute("aria-label", element.dataset[`${language}Aria`]);
  });
  document.querySelectorAll("[data-ja-alt][data-en-alt]").forEach((element) => {
    element.alt = element.dataset[`${language}Alt`];
  });
  document.title = document.querySelector("h1").textContent;
  updateColorPreview();
  scheduleMapPreview();
  updateGeotiffStatus();
  const selectedWrgCount = document.querySelector("#wrg_files").files.length;
  if (selectedWrgCount) {
    document.querySelector("#geotiff_error").textContent =
      currentLanguage().geotiffReady(selectedWrgCount);
  }
};
const minimumInput = document.querySelector("#color_minimum");
const maximumInput = document.querySelector("#color_maximum");
const divisionsInput = document.querySelector("#color_divisions");
const intervalInput = document.querySelector("#interval");
const intervalModeInput = document.querySelector("#interval_mode");
const previewRamp = document.querySelector("#preview_ramp");
const previewMinimum = document.querySelector("#preview_minimum");
const previewMaximum = document.querySelector("#preview_maximum");
const previewSummary = document.querySelector("#preview_summary");
const mrgFileInput = document.querySelector("#mrg_file");
const coordinateSystem = document.querySelector("#coordinate_system");
const utmZoneInput = document.querySelector("#utm_zone");
const utmHemisphereInput = document.querySelector("#utm_hemisphere");
const mapPreviewImage = document.querySelector("#map_preview_image");
const mapPreviewStatus = document.querySelector("#map_preview_status");
let mapPreviewController = null;
let mapPreviewTimer = null;
let mapPreviewUrl = null;
const formatNumber = (value) => Number(value.toFixed(2)).toString();
const updateColorPreview = () => {
  const minimum = Number(minimumInput.value);
  const maximum = Number(maximumInput.value);
  const divisions = Number(divisionsInput.value);
  const valid = Number.isFinite(minimum)
    && Number.isFinite(maximum)
    && minimum < maximum
    && Number.isInteger(divisions)
    && divisions >= 1
    && divisions <= maxColorDivisions;
  previewRamp.replaceChildren();
  if (!valid) {
    previewMinimum.textContent = "";
    previewMaximum.textContent = "";
    previewSummary.textContent = currentLanguage().invalidColorRange;
    return;
  }
  for (const color of colorPalettes[divisions]) {
    const segment = document.createElement("span");
    segment.style.backgroundColor = color;
    previewRamp.append(segment);
  }
  previewMinimum.textContent = `${formatNumber(minimum)} m/s`;
  previewMaximum.textContent = `${formatNumber(maximum)} m/s`;
  if (intervalModeInput.value === "linked") {
    intervalInput.value = formatNumber((maximum - minimum) / divisions);
  }
  previewSummary.textContent =
    currentLanguage().summary(divisions, formatNumber((maximum - minimum) / divisions));
};
const updateIntervalMode = () => {
  const linked = intervalModeInput.value === "linked";
  intervalInput.readOnly = linked;
  intervalInput.min = linked ? "0.001" : "0.1";
  if (linked) intervalInput.removeAttribute("max");
  else intervalInput.max = "100";
  if (linked) updateColorPreview();
};
const clearMapPreview = (status) => {
  mapPreviewController?.abort();
  mapPreviewController = null;
  clearTimeout(mapPreviewTimer);
  if (mapPreviewUrl) URL.revokeObjectURL(mapPreviewUrl);
  mapPreviewUrl = null;
  mapPreviewImage.hidden = true;
  mapPreviewImage.removeAttribute("src");
  mapPreviewStatus.textContent = status;
};
const updateMapPreview = async () => {
  const file = mrgFileInput.files[0];
  if (!file) {
    clearMapPreview(currentLanguage().missingFile);
    return;
  }
  if (!minimumInput.value || !maximumInput.value || !divisionsInput.value
      || !intervalInput.value || !minimumInput.validity.valid
      || !maximumInput.validity.valid || !divisionsInput.validity.valid
    || !intervalInput.validity.valid) {
    clearMapPreview(currentLanguage().invalidSettings);
    return;
  }
  if (file.name.toLowerCase().endsWith(".wrg")
      && (!utmZoneInput.value || !utmHemisphereInput.value)) {
    clearMapPreview(currentLanguage().missingWrgCrs);
    return;
  }
  mapPreviewController?.abort();
  const controller = new AbortController();
  mapPreviewController = controller;
  mapPreviewImage.hidden = true;
  mapPreviewStatus.textContent = currentLanguage().rendering;
  try {
    const response = await fetch("/preview", {
      method: "POST",
      body: new FormData(document.querySelector("#form")),
      signal: controller.signal,
    });
    if (!response.ok) {
      const message = await response.json();
      throw new Error(message.detail || currentLanguage().previewFailed);
    }
    const blob = await response.blob();
    if (controller.signal.aborted) return;
    if (mapPreviewUrl) URL.revokeObjectURL(mapPreviewUrl);
    mapPreviewUrl = URL.createObjectURL(blob);
    mapPreviewImage.src = mapPreviewUrl;
    mapPreviewImage.hidden = false;
    mapPreviewStatus.textContent = `${file.name}${currentLanguage().previewSuffix}`;
  } catch (error) {
    if (error.name !== "AbortError") {
      mapPreviewStatus.textContent = error.message;
    }
  }
};
const scheduleMapPreview = () => {
  clearTimeout(mapPreviewTimer);
  mapPreviewTimer = setTimeout(updateMapPreview, 250);
};
const updateCoordinateSystem = () => {
  const file = mrgFileInput.files[0];
  const isWrg = file?.name.toLowerCase().endsWith(".wrg") ?? false;
  coordinateSystem.hidden = !isWrg;
  utmZoneInput.required = isWrg;
  utmHemisphereInput.required = isWrg;
};
[minimumInput, maximumInput, divisionsInput].forEach((input) => {
  input.addEventListener("input", () => {
    updateColorPreview();
    scheduleMapPreview();
  });
});
intervalModeInput.addEventListener("change", () => {
  updateIntervalMode();
  scheduleMapPreview();
});
intervalInput.addEventListener("input", scheduleMapPreview);
mrgFileInput.addEventListener("change", () => {
  updateCoordinateSystem();
  scheduleMapPreview();
});
[utmZoneInput, utmHemisphereInput].forEach((input) => {
  input.addEventListener("change", scheduleMapPreview);
});
languageInput.addEventListener("change", applyLanguage);
updateCoordinateSystem();
updateIntervalMode();
updateColorPreview();

const opacityInput = document.querySelector("#kmz_opacity_percent");
const opacityValue = document.querySelector("#opacity_value");
opacityInput.addEventListener("input", () => {
  opacityValue.value = `${opacityInput.value}%`;
  scheduleMapPreview();
});
["#show_legend_title", "#legend_position"].forEach((selector) => {
  document.querySelector(selector).addEventListener("change", scheduleMapPreview);
});
document.querySelector("#form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.querySelector("#error");
  error.textContent = "";
  const button = event.target.querySelector("button");
  button.disabled = true;
  button.textContent = currentLanguage().converting;
  try {
    const response = await fetch("/convert", { method: "POST", body: new FormData(event.target) });
    if (!response.ok) {
      const message = await response.json();
      throw new Error(message.detail || "変換に失敗しました。");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    const now = new Date();
    const timestamp = [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, "0"),
      String(now.getDate()).padStart(2, "0"),
      "_",
      String(now.getHours()).padStart(2, "0"),
      String(now.getMinutes()).padStart(2, "0"),
      String(now.getSeconds()).padStart(2, "0"),
    ].join("");
    link.download = `${timestamp}_mascot_wind_contours.zip`;
    link.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    error.textContent = err.message;
  } finally {
    button.disabled = false;
    button.textContent = currentLanguage().convert;
  }
});

const selectTab = (tabId) => {
  const colored = tabId === "colored-tab";
  document.querySelector("#colored-tab").classList.toggle("active", colored);
  document.querySelector("#colored-tab").setAttribute("aria-selected", String(colored));
  document.querySelector("#geotiff-tab").classList.toggle("active", !colored);
  document.querySelector("#geotiff-tab").setAttribute("aria-selected", String(!colored));
  document.querySelector("#colored-panel").hidden = !colored;
  document.querySelector("#geotiff-panel").hidden = colored;
};
document.querySelector("#colored-tab").addEventListener("click", () => selectTab("colored-tab"));
document.querySelector("#geotiff-tab").addEventListener("click", () => selectTab("geotiff-tab"));

const wrgFilesInput = document.querySelector("#wrg_files");
const wrgFileSettings = document.querySelector("#wrg_file_settings");
const renderWrgFileSettings = () => {
  geotiffProgressState = null;
  document.querySelector("#geotiff_progress_container").hidden = true;
  wrgFileSettings.replaceChildren();
  const files = Array.from(wrgFilesInput.files || []);
  files.forEach((file, index) => {
    const fieldset = document.createElement("fieldset");
    fieldset.className = "wrg-file-setting";
    const legend = document.createElement("legend");
    legend.className = "wrg-file-name";
    legend.textContent = file.name;
    fieldset.append(legend);

    const controls = document.createElement("div");
    controls.className = "utm-controls";
    const zoneField = document.createElement("div");
    zoneField.className = "utm-field";
    const zoneLabel = document.createElement("label");
    zoneLabel.htmlFor = `wrg_zone_${index}`;
    zoneLabel.dataset.ja = currentLanguage().zoneNumber;
    zoneLabel.dataset.en = translations.en.zoneNumber;
    zoneLabel.textContent = currentLanguage().zoneNumber;
    const zoneSelect = document.createElement("select");
    zoneSelect.id = `wrg_zone_${index}`;
    zoneSelect.name = "utm_zones";
    zoneSelect.required = true;
    for (let zone = 1; zone <= 60; zone += 1) {
      const option = document.createElement("option");
      option.value = String(zone);
      option.textContent = String(zone);
      if (zone === 54) option.selected = true;
      zoneSelect.append(option);
    }
    zoneField.append(zoneLabel, zoneSelect);

    const hemisphereField = document.createElement("div");
    hemisphereField.className = "utm-field";
    const hemisphereLabel = document.createElement("label");
    hemisphereLabel.htmlFor = `wrg_hemisphere_${index}`;
    hemisphereLabel.dataset.ja = currentLanguage().hemisphere;
    hemisphereLabel.dataset.en = translations.en.hemisphere;
    hemisphereLabel.textContent = currentLanguage().hemisphere;
    const hemisphereSelect = document.createElement("select");
    hemisphereSelect.id = `wrg_hemisphere_${index}`;
    hemisphereSelect.name = "utm_hemispheres";
    hemisphereSelect.required = true;
    for (const hemisphere of ["N", "S"]) {
      const option = document.createElement("option");
      option.value = hemisphere;
      option.textContent = hemisphere;
      if (hemisphere === "N") option.selected = true;
      hemisphereSelect.append(option);
    }
    hemisphereField.append(hemisphereLabel, hemisphereSelect);

    controls.append(zoneField, hemisphereField);
    fieldset.append(controls);
    wrgFileSettings.append(fieldset);
  });
  if (files.length) {
    document.querySelector("#geotiff_error").textContent =
      currentLanguage().geotiffReady(files.length);
  }
};
wrgFilesInput.addEventListener("change", renderWrgFileSettings);

document.querySelector("#geotiff_form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.querySelector("#geotiff_error");
  const button = document.querySelector("#geotiff_submit");
  const progressContainer = document.querySelector("#geotiff_progress_container");
  const progress = document.querySelector("#geotiff_progress");
  const count = wrgFilesInput.files.length;
  const formData = new FormData(event.target);
  error.textContent = "";
  button.disabled = true;
  wrgFilesInput.disabled = true;
  button.textContent = currentLanguage().geotiffConverting;
  progressContainer.hidden = false;
  progress.max = 100;
  progress.value = 0;
  geotiffProgressState = { phase: "uploading", count, startedAt: Date.now() };
  updateGeotiffStatus();
  const statusTimer = window.setInterval(updateGeotiffStatus, 1000);
  try {
    const blob = await new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", "/convert-wrg-geotiffs");
      request.responseType = "blob";
      request.upload.addEventListener("progress", (uploadEvent) => {
        if (uploadEvent.lengthComputable) {
          geotiffProgressState.percent = Math.round(
            (uploadEvent.loaded / uploadEvent.total) * 100,
          );
          updateGeotiffStatus();
        }
      });
      request.upload.addEventListener("load", () => {
        geotiffProgressState.phase = "processing";
        updateGeotiffStatus();
      });
      request.addEventListener("load", async () => {
        if (request.status < 200 || request.status >= 300) {
          try {
            const body = JSON.parse(await request.response.text());
            const detail = Array.isArray(body.detail)
              ? body.detail.map((item) => item.msg).filter(Boolean).join("\n")
              : body.detail;
            reject(new Error(detail || currentLanguage().geotiffError));
          } catch (err) {
            reject(err instanceof SyntaxError ? new Error(currentLanguage().geotiffError) : err);
          }
          return;
        }
        resolve(request.response);
      });
      request.addEventListener("error", () => reject(new Error(currentLanguage().geotiffError)));
      request.addEventListener("abort", () => reject(new Error(currentLanguage().geotiffError)));
      request.send(formData);
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    const now = new Date();
    const timestamp = [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, "0"),
      String(now.getDate()).padStart(2, "0"),
      "_",
      String(now.getHours()).padStart(2, "0"),
      String(now.getMinutes()).padStart(2, "0"),
      String(now.getSeconds()).padStart(2, "0"),
    ].join("");
    link.download = `${timestamp}_wind_speed_geotiffs.zip`;
    link.click();
    URL.revokeObjectURL(url);
    geotiffProgressState.phase = "complete";
    updateGeotiffStatus();
  } catch (err) {
    error.textContent = err.message;
    geotiffProgressState = null;
    progressContainer.hidden = true;
  } finally {
    window.clearInterval(statusTimer);
    button.disabled = false;
    wrgFilesInput.disabled = false;
    button.textContent = currentLanguage().geotiffDownload;
  }
});
