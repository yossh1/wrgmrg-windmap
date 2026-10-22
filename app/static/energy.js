const powerCurveInput = document.querySelector("#power_curve_files");
const powerCurveStatus = document.querySelector("#power_curve_status");
const powerCurvePreviews = document.querySelector("#power_curve_previews");
let powerCurvePreviewRequest = 0;

const renderPowerCurve = (chart, points) => {
  const width = 640;
  const height = 360;
  const margin = { top: 20, right: 24, bottom: 54, left: 68 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const maxWindSpeed = Math.max(...points.map((point) => point.wind_speed));
  const yMaximum = Math.max(1, ...points.map((point) => point.power_kw)) * 1.1;
  const x = (value) => margin.left + (value / maxWindSpeed) * plotWidth;
  const y = (value) => margin.top + plotHeight - (value / yMaximum) * plotHeight;
  const namespace = "http://www.w3.org/2000/svg";
  const add = (tag, attributes, text) => {
    const element = document.createElementNS(namespace, tag);
    for (const [name, value] of Object.entries(attributes)) {
      element.setAttribute(name, String(value));
    }
    if (text !== undefined) element.textContent = text;
    chart.append(element);
  };

  chart.replaceChildren();
  for (let index = 0; index <= 4; index += 1) {
    const value = (yMaximum * index) / 4;
    add("line", {
      x1: margin.left,
      x2: width - margin.right,
      y1: y(value),
      y2: y(value),
      stroke: "#dadce0",
    });
    add("text", {
      x: margin.left - 8,
      y: y(value) + 4,
      "text-anchor": "end",
      fill: "#444",
      "font-size": 12,
    }, formatNumber(value));
  }
  add("line", {
    x1: margin.left,
    x2: margin.left,
    y1: margin.top,
    y2: margin.top + plotHeight,
    stroke: "#555",
  });
  add("line", {
    x1: margin.left,
    x2: width - margin.right,
    y1: margin.top + plotHeight,
    y2: margin.top + plotHeight,
    stroke: "#555",
  });
  add("text", {
    x: margin.left + plotWidth / 2,
    y: height - 10,
    "text-anchor": "middle",
    fill: "#202124",
    "font-size": 14,
  }, currentLanguage().powerCurveWindAxis);
  add("text", {
    x: 18,
    y: margin.top + plotHeight / 2,
    transform: `rotate(-90 18 ${margin.top + plotHeight / 2})`,
    "text-anchor": "middle",
    fill: "#202124",
    "font-size": 14,
  }, currentLanguage().powerCurvePowerAxis);
  add("polyline", {
    points: points.map((point) => `${x(point.wind_speed)},${y(point.power_kw)}`).join(" "),
    fill: "none",
    stroke: "#1769aa",
    "stroke-width": 3,
    "stroke-linejoin": "round",
    "stroke-linecap": "round",
  });
  points.forEach((point) => add("circle", {
    cx: x(point.wind_speed),
    cy: y(point.power_kw),
    r: 3,
    fill: "#1769aa",
  }));
  add("text", {
    x: margin.left,
    y: margin.top + plotHeight + 22,
    "text-anchor": "middle",
    fill: "#444",
    "font-size": 12,
  }, "0");
  add("text", {
    x: width - margin.right,
    y: margin.top + plotHeight + 22,
    "text-anchor": "middle",
    fill: "#444",
    "font-size": 12,
  }, formatNumber(maxWindSpeed));
  chart.hidden = false;
};

window.renderPowerCurvePreviews = () => {
  powerCurvePreviews.replaceChildren();
  if (powerCurvePreviewPhase === "missing") {
    powerCurveStatus.textContent = currentLanguage().powerCurveMissing;
  } else if (powerCurvePreviewPhase === "loading") {
    powerCurveStatus.textContent = currentLanguage().powerCurveLoading;
  } else if (powerCurvePreviewPhase === "ready") {
    const pointCount = currentPowerCurvePoints.reduce(
      (sum, preview) => sum + preview.points.length,
      0,
    );
    powerCurveStatus.textContent = currentLanguage().powerCurvePreviewsReady(
      currentPowerCurvePoints.length,
      pointCount,
    );
  }
  const previews = currentPowerCurvePoints;
  if (!previews.length) return;
  const width = 640;
  const height = 390;
  const margin = { top: 20, right: 24, bottom: 54, left: 68 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const maxWindSpeed = Math.max(...previews.flatMap(({ points }) =>
    points.map((point) => point.wind_speed)));
  const yMaximum = Math.max(1, ...previews.flatMap(({ points }) =>
    points.map((point) => point.power_kw))) * 1.1;
  const x = (value) => margin.left + (value / maxWindSpeed) * plotWidth;
  const y = (value) => margin.top + plotHeight - (value / yMaximum) * plotHeight;
  const namespace = "http://www.w3.org/2000/svg";
  const chart = document.createElementNS(namespace, "svg");
  chart.setAttribute("viewBox", `0 0 ${width} ${height}`);
  chart.setAttribute("role", "img");
  chart.setAttribute("aria-label", currentLanguage().powerCurvePreviewLabel);
  const add = (tag, attributes, text) => {
    const element = document.createElementNS(namespace, tag);
    for (const [name, value] of Object.entries(attributes)) {
      element.setAttribute(name, String(value));
    }
    if (text !== undefined) element.textContent = text;
    chart.append(element);
  };

  for (let index = 0; index <= 4; index += 1) {
    const value = (yMaximum * index) / 4;
    add("line", {
      x1: margin.left,
      x2: width - margin.right,
      y1: y(value),
      y2: y(value),
      stroke: "#dadce0",
    });
    add("text", {
      x: margin.left - 8,
      y: y(value) + 4,
      "text-anchor": "end",
      fill: "#444",
      "font-size": 12,
    }, formatNumber(value));
  }
  add("line", {
    x1: margin.left, x2: margin.left, y1: margin.top, y2: margin.top + plotHeight, stroke: "#555",
  });
  add("line", {
    x1: margin.left,
    x2: width - margin.right,
    y1: margin.top + plotHeight,
    y2: margin.top + plotHeight,
    stroke: "#555",
  });
  add("text", {
    x: margin.left + plotWidth / 2,
    y: height - 10,
    "text-anchor": "middle",
    fill: "#202124",
    "font-size": 14,
  }, currentLanguage().powerCurveWindAxis);
  add("text", {
    x: 18,
    y: margin.top + plotHeight / 2,
    transform: `rotate(-90 18 ${margin.top + plotHeight / 2})`,
    "text-anchor": "middle",
    fill: "#202124",
    "font-size": 14,
  }, currentLanguage().powerCurvePowerAxis);
  add("text", {
    x: margin.left,
    y: margin.top + plotHeight + 22,
    "text-anchor": "middle",
    fill: "#444",
    "font-size": 12,
  }, "0");
  add("text", {
    x: width - margin.right,
    y: margin.top + plotHeight + 22,
    "text-anchor": "middle",
    fill: "#444",
    "font-size": 12,
  }, formatNumber(maxWindSpeed));

  const legend = document.createElement("ul");
  legend.className = "power-curve-legend";
  previews.forEach((preview, index) => {
    const color = `hsl(${(index * 137.508) % 360} 65% 43%)`;
    const points = preview.points;
    add("polyline", {
      points: points.map((point) => `${x(point.wind_speed)},${y(point.power_kw)}`).join(" "),
      fill: "none",
      stroke: color,
      "stroke-width": 3,
      "stroke-linejoin": "round",
      "stroke-linecap": "round",
    });
    points.forEach((point) => add("circle", {
      cx: x(point.wind_speed),
      cy: y(point.power_kw),
      r: 3,
      fill: color,
    }));
    const item = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = "power-curve-legend-swatch";
    swatch.style.backgroundColor = color;
    swatch.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.textContent = preview.name;
    item.append(swatch, label);
    legend.append(item);
  });
  powerCurvePreviews.append(chart, legend);
};

powerCurveInput.addEventListener("change", async () => {
  const requestId = ++powerCurvePreviewRequest;
  const files = Array.from(powerCurveInput.files || []);
  energyProgressState = null;
  document.querySelector("#energy_progress_container").hidden = true;
  const wrgCount = document.querySelector("#energy_wrg_files").files.length;
  document.querySelector("#energy_error").textContent = wrgCount
    ? currentLanguage().energyReady(wrgCount, files.length)
    : "";
  currentPowerCurvePoints = [];
  powerCurvePreviews.replaceChildren();
  if (!files.length) {
    powerCurvePreviewPhase = "missing";
    powerCurveStatus.textContent = currentLanguage().powerCurveMissing;
    return;
  }

  powerCurvePreviewPhase = "loading";
  powerCurveStatus.textContent = currentLanguage().powerCurveLoading;
  try {
    const previews = await Promise.all(files.map(async (file) => {
      const formData = new FormData();
      formData.append("power_curve_file", file);
      const response = await fetch("/preview-power-curve", { method: "POST", body: formData });
      const result = await response.json();
      if (!response.ok) {
        const detail = Array.isArray(result.detail)
          ? result.detail.map((item) => item.msg).filter(Boolean).join("\n")
          : result.detail;
        throw new Error(`${file.name}: ${detail || currentLanguage().energyError}`);
      }
      return { name: file.name, points: result.points };
    }));
    if (requestId !== powerCurvePreviewRequest) return;
    currentPowerCurvePoints = previews;
    powerCurvePreviewPhase = "ready";
    window.renderPowerCurvePreviews();
    const pointCount = previews.reduce((sum, preview) => sum + preview.points.length, 0);
    powerCurveStatus.textContent = currentLanguage().powerCurvePreviewsReady(
      previews.length,
      pointCount,
    );
    const wrgCount = document.querySelector("#energy_wrg_files").files.length;
    document.querySelector("#energy_error").textContent = wrgCount
      ? currentLanguage().energyReady(wrgCount, previews.length)
      : "";
  } catch (err) {
    if (requestId !== powerCurvePreviewRequest) return;
    powerCurvePreviewPhase = "error";
    powerCurveStatus.textContent = err.message;
  }
});

document.querySelector("#energy_wrg_files").addEventListener("change", (event) => {
  energyProgressState = null;
  document.querySelector("#energy_progress_container").hidden = true;
  const files = Array.from(event.target.files || []);
  createWrgFileSettings(files, document.querySelector("#energy_wrg_file_settings"));
  document.querySelector("#energy_error").textContent = files.length
    ? currentLanguage().energyReady(files.length, powerCurveInput.files.length)
    : "";
});

document.querySelector("#energy_form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const filesInput = document.querySelector("#energy_wrg_files");
  const curveFiles = Array.from(powerCurveInput.files || []);
  const button = document.querySelector("#energy_submit");
  const error = document.querySelector("#energy_error");
  const formData = new FormData(event.target);
  error.textContent = "";
  button.disabled = true;
  filesInput.disabled = true;
  powerCurveInput.disabled = true;
  button.textContent = currentLanguage().energyConverting;
  try {
    await window.submitConversionJob({
      kind: "energy",
      form: event.target,
      formData,
      endpoint: "/conversion-jobs/annual-energy",
      filename: "annual_energy_geotiffs.zip",
      jobCount: filesInput.files.length * curveFiles.length,
      wrgCount: filesInput.files.length,
      curveCount: curveFiles.length,
    });
  } catch (err) {
    window.markConversionJobFailed("energy");
    error.textContent = err.message;
  } finally {
    button.disabled = false;
    filesInput.disabled = false;
    powerCurveInput.disabled = false;
    button.textContent = currentLanguage().energyDownload;
  }
});
