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
    geotiffUploading: (count, percent, eta) => `${count}個のファイルをアップロード中... ${percent}%（全体 ${Math.round(percent * 0.1)}%）${eta}`,
    geotiffProcessing: (count, elapsed) => `${count}個のファイルを変換中です。経過時間: ${elapsed}秒`,
    geotiffComplete: (count) => `${count}個のGeoTIFFをZIPでダウンロードしました。`,
    geotiffError: "GeoTIFFを作成できませんでした。",
    energyConverting: "発電量マップを作成中...",
    energyDownload: "年間発電量GeoTIFFをZIPでダウンロード",
    energyReady: (wrgCount, curveCount) => `${wrgCount}個のWRGと${curveCount}個のパワーカーブから${wrgCount * curveCount}個の年間発電量マップを作成します。`,
    energyUploading: (wrgCount, curveCount, percent, eta) => `${wrgCount}個のWRGと${curveCount}個のパワーカーブ（計${wrgCount * curveCount}マップ分）をアップロード中... ${percent}%（全体 ${Math.round(percent * 0.1)}%）${eta}`,
    energyProcessing: (count, elapsed) => `${count}個の年間発電量マップを計算中です。経過時間: ${elapsed}秒`,
    energyComplete: (count) => `${count}個の年間発電量GeoTIFFをZIPでダウンロードしました。`,
    energyError: "年間発電量マップを作成できませんでした。",
    jobProgress: (stage, percent, eta) => `${stage} — 全体 ${percent}%${eta}`,
    etaEstimating: "（残り時間を推定中）",
    uploadLog: (count) => `${count}個の入力ファイルを送信中`,
    uploadStage: "アップロード中",
    overallUploading: "アップロード",
    jobFileProgress: (name, stage, percent) => `${name} — ${stage} ${percent}%`,
    jobStages: {
      queued: "待機中", processing: "処理中", analysis: "解析中", parsing: "WRG解析中",
      calculating: "発電量計算中", writing: "GeoTIFF書き出し中",
      packaging: "ZIP格納中", complete: "完了", failed: "失敗",
    },
    powerCurveLoading: "パワーカーブを読み込み中...",
    powerCurveReady: (count) => `${count}点のパワーカーブを表示しています。`,
    powerCurvePreviewsReady: (curves, points) => `${curves}個のパワーカーブ（合計${points}点）をプレビューしています。`,
    powerCurvePreviewLabel: "パワーカーブプレビュー",
    powerCurveMissing: "CSVを選択すると、パワーカーブをプレビューします。",
    powerCurveWindAxis: "風速 (m/s)",
    powerCurvePowerAxis: "出力 (kW)",
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
    geotiffUploading: (count, percent, eta) => `Uploading ${count} files... ${percent}% (overall ${Math.round(percent * 0.1)}%)${eta}`,
    geotiffProcessing: (count, elapsed) => `Converting ${count} files. Elapsed: ${elapsed}s`,
    geotiffComplete: (count) => `Downloaded a ZIP containing ${count} GeoTIFFs.`,
    geotiffError: "Could not create the GeoTIFFs.",
    energyConverting: "Creating annual energy maps...",
    energyDownload: "Download annual energy GeoTIFFs as ZIP",
    energyReady: (wrgCount, curveCount) => `${wrgCount} WRG files × ${curveCount} power curves = ${wrgCount * curveCount} annual energy maps.`,
    energyUploading: (wrgCount, curveCount, percent, eta) => `Uploading ${wrgCount} WRG files and ${curveCount} power curves (${wrgCount * curveCount} maps)... ${percent}% (overall ${Math.round(percent * 0.1)}%)${eta}`,
    energyProcessing: (count, elapsed) => `Calculating ${count} annual energy maps. Elapsed: ${elapsed}s`,
    energyComplete: (count) => `Downloaded a ZIP containing ${count} annual energy GeoTIFFs.`,
    energyError: "Could not create the annual energy maps.",
    jobProgress: (stage, percent, eta) => `${stage} — Overall ${percent}%${eta}`,
    etaEstimating: " · estimating remaining time",
    uploadLog: (count) => `Uploading ${count} input files`,
    uploadStage: "Uploading",
    overallUploading: "Upload",
    jobFileProgress: (name, stage, percent) => `${name} — ${stage} ${percent}%`,
    jobStages: {
      queued: "Queued", processing: "Processing", analysis: "Analyzing", parsing: "Parsing WRG",
      calculating: "Calculating AEP", writing: "Writing GeoTIFF",
      packaging: "Adding files to ZIP", complete: "Complete", failed: "Failed",
    },
    powerCurveLoading: "Loading the power curve...",
    powerCurveReady: (count) => `Showing ${count} power curve points.`,
    powerCurvePreviewsReady: (curves, points) => `Previewing ${curves} power curves (${points} points total).`,
    powerCurvePreviewLabel: "power curve preview",
    powerCurveMissing: "Select a CSV file to preview the power curve.",
    powerCurveWindAxis: "Wind speed (m/s)",
    powerCurvePowerAxis: "Power (kW)",
    previewSuffix: " wind speed contour map",
    summary: (divisions, interval) => `${divisions} divisions · ${interval} m/s interval`,
  },
};
const languageInput = document.querySelector("#language");
const currentLanguage = () => translations[languageInput.value];
const formatRemainingTime = (seconds) => {
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  const rounded = Math.max(1, Math.round(seconds));
  if (languageInput.value === "en") {
    return rounded < 60 ? ` · about ${rounded}s remaining` : ` · about ${Math.ceil(rounded / 60)}m remaining`;
  }
  return rounded < 60 ? `（残り約${rounded}秒）` : `（残り約${Math.ceil(rounded / 60)}分）`;
};
const estimateRemainingTime = (state) => {
  const startedAt = state.overallStartedAt || state.uploadStartedAt;
  const progress = state.phase === "uploading"
    ? Math.round((state.uploadProgress || 0) * 0.1)
    : state.progress;
  if (!startedAt || progress <= 0 || progress >= 100) return null;
  const elapsedSeconds = (Date.now() - startedAt) / 1000;
  if (elapsedSeconds < 5) return null;
  return {
    seconds: elapsedSeconds * (100 - progress) / progress,
  };
};
let geotiffProgressState = null;
let energyProgressState = null;
let powerCurvePreviewPhase = "missing";
let currentPowerCurvePoints = [];
const renderConversionProgress = (kind) => {
  const state = kind === "geotiff" ? geotiffProgressState : energyProgressState;
  if (!state) return;
  const progress = document.querySelector(`#${kind}_progress`);
  const status = document.querySelector(`#${kind}_status`);
  const logs = document.querySelector(`#${kind}_file_logs`);
  const renderLog = (name, stage, percent, error = "") => {
    const item = document.createElement("li");
    const nameCell = document.createElement("span");
    nameCell.className = "conversion-file-name";
    nameCell.textContent = name;
    const stageCell = document.createElement("span");
    stageCell.className = "conversion-file-stage";
    stageCell.textContent =
      `${stage} ${percent}%${error ? `: ${error}` : ""}`;
    item.append(nameCell, stageCell);
    logs.append(item);
  };
  if (state.phase === "uploading") {
    logs.replaceChildren();
    progress.value = Math.round((state.uploadProgress || 0) * 0.1);
    const eta = estimateRemainingTime(state);
    const uploadProgress = state.uploadProgress || 0;
    const uploadName = kind === "geotiff"
      ? currentLanguage().uploadLog(state.count)
      : currentLanguage().uploadLog(state.wrgCount + state.curveCount);
    renderLog(uploadName, currentLanguage().uploadStage, uploadProgress);
    status.textContent = currentLanguage().jobProgress(
      currentLanguage().overallUploading,
      Math.round(uploadProgress * 0.1),
      eta
        ? formatRemainingTime(eta.seconds)
        : currentLanguage().etaEstimating,
    );
    return;
  }
  progress.value = state.progress ?? 0;
  if (state.phase === "complete") {
    logs.replaceChildren();
    for (const file of state.files || []) {
      renderLog(
        file.name,
        currentLanguage().jobStages.complete,
        100,
      );
    }
    status.textContent = currentLanguage().jobProgress(
      currentLanguage().jobStages.complete,
      100,
      "",
    );
    return;
  }
  const stage = currentLanguage().jobStages[state.stage] || state.stage;
  const eta = estimateRemainingTime(state);
  status.textContent = currentLanguage().jobProgress(
    stage,
    state.progress || 0,
    eta
      ? formatRemainingTime(eta.seconds)
      : state.stage === "failed" || state.stage === "complete"
        ? ""
        : currentLanguage().etaEstimating,
  );
  logs.replaceChildren();
  for (const file of state.files || []) {
    const fileStage = currentLanguage().jobStages[file.stage] || file.stage;
    renderLog(file.name, fileStage, file.progress, file.error);
  }
};
const updateGeotiffStatus = () => {
  renderConversionProgress("geotiff");
};
const updateEnergyStatus = () => {
  renderConversionProgress("energy");
};

window.markConversionJobFailed = (kind) => {
  const state = kind === "geotiff" ? geotiffProgressState : energyProgressState;
  if (state) {
    state.phase = "server";
    state.stage = "failed";
    renderConversionProgress(kind);
  }
};
window.submitConversionJob = async ({
  kind,
  form,
  formData,
  endpoint,
  filename,
  jobCount,
  wrgCount,
  curveCount,
}) => {
  const inputCount = form.querySelector('input[type="file"][multiple]').files.length;
  const startedAt = Date.now();
  const state = {
    phase: "uploading",
    count: jobCount ?? inputCount,
    wrgCount,
    curveCount,
    percent: 0,
    uploadProgress: 0,
    uploadedBytes: 0,
    uploadTotal: 0,
    uploadStartedAt: startedAt,
    overallStartedAt: startedAt,
    files: [],
  };
  if (kind === "geotiff") geotiffProgressState = state;
  else energyProgressState = state;
  document.querySelector(`#${kind}_progress_container`).hidden = false;
  renderConversionProgress(kind);
  const job = await new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", endpoint);
    request.responseType = "json";
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        state.uploadedBytes = event.loaded;
        state.uploadTotal = event.total;
        state.uploadProgress = Math.round((event.loaded / event.total) * 100);
        renderConversionProgress(kind);
      }
    });
    request.addEventListener("load", () => {
      if (request.status < 200 || request.status >= 300) {
        const detail = request.response?.detail;
        reject(new Error(Array.isArray(detail)
          ? detail.map((item) => item.msg).filter(Boolean).join("\n")
          : detail || currentLanguage()[`${kind}Error`]));
      } else {
        resolve(request.response);
      }
    });
    request.addEventListener("error", () => reject(new Error(currentLanguage()[`${kind}Error`])));
    request.addEventListener("abort", () => reject(new Error(currentLanguage()[`${kind}Error`])));
    request.send(formData);
  });
  state.phase = "server";
  state.stage = "analysis";
  state.progress = 10;
  renderConversionProgress(kind);
  let result;
  do {
    await new Promise((resolve) => window.setTimeout(resolve, 700));
    const response = await fetch(`/conversion-jobs/${encodeURIComponent(job.id)}`);
    if (!response.ok) throw new Error(currentLanguage()[`${kind}Error`]);
    result = await response.json();
    Object.assign(state, result, { phase: "server" });
    renderConversionProgress(kind);
    if (result.status === "failed") {
      throw new Error(result.files.find((file) => file.error)?.error || result.error
        || currentLanguage()[`${kind}Error`]);
    }
  } while (result.status !== "complete");
  const downloadResponse = await fetch(
    `/conversion-jobs/${encodeURIComponent(job.id)}/download`,
  );
  if (!downloadResponse.ok) throw new Error(currentLanguage()[`${kind}Error`]);
  const blob = await downloadResponse.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const now = new Date();
  const timestamp = [
    now.getFullYear(), String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"), "_",
    String(now.getHours()).padStart(2, "0"),
    String(now.getMinutes()).padStart(2, "0"),
    String(now.getSeconds()).padStart(2, "0"),
  ].join("");
  link.download = `${timestamp}_${filename}`;
  link.click();
  URL.revokeObjectURL(url);
  state.phase = "complete";
  renderConversionProgress(kind);
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
  updateEnergyStatus();
  if (window.renderPowerCurvePreviews) window.renderPowerCurvePreviews();
  const selectedWrgCount = document.querySelector("#wrg_files").files.length;
  if (selectedWrgCount) {
    document.querySelector("#geotiff_error").textContent =
      currentLanguage().geotiffReady(selectedWrgCount);
  }
  const selectedEnergyWrgCount = document.querySelector("#energy_wrg_files").files.length;
  if (selectedEnergyWrgCount && !energyProgressState) {
    document.querySelector("#energy_error").textContent =
      currentLanguage().energyReady(
        selectedEnergyWrgCount,
        document.querySelector("#power_curve_files").files.length,
      );
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
    window.markConversionJobFailed("geotiff");
    error.textContent = err.message;
  } finally {
    button.disabled = false;
    button.textContent = currentLanguage().convert;
  }
});

const selectTab = (tabId) => {
  for (const [id, panelId] of [
    ["colored-tab", "colored-panel"],
    ["mean-tab", "mean-panel"],
    ["energy-tab", "energy-panel"],
  ]) {
    const selected = tabId === id;
    document.querySelector(`#${id}`).classList.toggle("active", selected);
    document.querySelector(`#${id}`).setAttribute("aria-selected", String(selected));
    document.querySelector(`#${panelId}`).hidden = !selected;
  }
};
document.querySelector("#colored-tab").addEventListener("click", () => selectTab("colored-tab"));
document.querySelector("#mean-tab").addEventListener("click", () => selectTab("mean-tab"));
document.querySelector("#energy-tab").addEventListener("click", () => selectTab("energy-tab"));

const createWrgFileSettings = (files, settingsContainer) => {
  settingsContainer.replaceChildren();
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
    settingsContainer.append(fieldset);
  });
};

const wrgFilesInput = document.querySelector("#wrg_files");
const energyWrgFilesInput = document.querySelector("#energy_wrg_files");
const renderWrgFileSettings = () => {
  geotiffProgressState = null;
  document.querySelector("#geotiff_progress_container").hidden = true;
  const files = Array.from(wrgFilesInput.files || []);
  createWrgFileSettings(files, document.querySelector("#wrg_file_settings"));
  if (files.length) {
    document.querySelector("#geotiff_error").textContent =
      currentLanguage().geotiffReady(files.length);
  }
};
wrgFilesInput.addEventListener("change", renderWrgFileSettings);
energyWrgFilesInput.addEventListener("change", () => {
  energyProgressState = null;
  document.querySelector("#energy_progress_container").hidden = true;
  const files = Array.from(energyWrgFilesInput.files || []);
  createWrgFileSettings(files, document.querySelector("#energy_wrg_file_settings"));
  document.querySelector("#energy_error").textContent = files.length
    ? currentLanguage().energyReady(
      files.length,
      document.querySelector("#power_curve_files").files.length,
    )
    : "";
});

document.querySelector("#geotiff_form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.querySelector("#geotiff_error");
  const button = document.querySelector("#geotiff_submit");
  const formData = new FormData(event.target);
  error.textContent = "";
  button.disabled = true;
  wrgFilesInput.disabled = true;
  button.textContent = currentLanguage().geotiffConverting;
  try {
    await window.submitConversionJob({
      kind: "geotiff",
      form: event.target,
      formData,
      endpoint: "/conversion-jobs/mean-wind-speed",
      filename: "wind_speed_geotiffs.zip",
    });
  } catch (err) {
    error.textContent = err.message;
  } finally {
    button.disabled = false;
    wrgFilesInput.disabled = false;
    button.textContent = currentLanguage().geotiffDownload;
  }
});
