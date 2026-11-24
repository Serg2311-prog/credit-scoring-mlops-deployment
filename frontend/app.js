(() => {
  const form = document.getElementById("score-form");
  const statusEl = document.getElementById("api-status");
  const resultEl = document.getElementById("result");
  const errorEl = document.getElementById("error");
  const submitBtn = document.getElementById("submit-btn");
  const fillDemoBtn = document.getElementById("fill-demo");

  const DEMO = {
    LIMIT_BAL: 20000,
    SEX: 2,
    EDUCATION: 2,
    MARRIAGE: 1,
    AGE: 24,
    PAY_0: 2,
    PAY_2: 2,
    PAY_3: -1,
    PAY_4: -1,
    PAY_5: -2,
    PAY_6: -2,
    BILL_AMT1: 3913,
    BILL_AMT2: 3102,
    BILL_AMT3: 689,
    BILL_AMT4: 0,
    BILL_AMT5: 0,
    BILL_AMT6: 0,
    PAY_AMT1: 0,
    PAY_AMT2: 689,
    PAY_AMT3: 0,
    PAY_AMT4: 0,
    PAY_AMT5: 0,
    PAY_AMT6: 0,
  };

  function showError(message) {
    errorEl.hidden = false;
    errorEl.textContent = message;
  }

  function clearError() {
    errorEl.hidden = true;
    errorEl.textContent = "";
  }

  function readPayload(formEl) {
    const data = new FormData(formEl);
    const payload = {};
    for (const [key, raw] of data.entries()) {
      const value = Number(raw);
      if (Number.isNaN(value)) {
        throw new Error(`Некорректное число в поле ${key}`);
      }
      payload[key] = value;
    }
    return payload;
  }

  function fillDemo() {
    for (const [key, value] of Object.entries(DEMO)) {
      const field = form.elements.namedItem(key);
      if (field) field.value = String(value);
    }
  }

  async function checkApi() {
    try {
      const response = await fetch("/api/health/ready", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`ready HTTP ${response.status}`);
      }
      const body = await response.json();
      statusEl.className = "status-row ok";
      statusEl.textContent = `API готов · model=${body.model_version || "onnx"}`;
      return true;
    } catch (err) {
      statusEl.className = "status-row bad";
      statusEl.textContent = `API недоступен: ${err.message}`;
      return false;
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    resultEl.hidden = true;
    submitBtn.disabled = true;
    try {
      const payload = readPayload(form);
      const response = await fetch("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail =
          body.detail ||
          body.message ||
          body.error_code ||
          JSON.stringify(body) ||
          response.statusText;
        throw new Error(`Ошибка ${response.status}: ${detail}`);
      }
      document.getElementById("out-proba").textContent = Number(
        body.probability_default
      ).toFixed(6);
      document.getElementById("out-pred").textContent =
        body.prediction === 1 ? "1 — риск дефолта" : "0 — низкий риск";
      document.getElementById("out-model").textContent = body.model_version || "—";
      document.getElementById("out-rid").textContent = body.request_id || "—";
      document.getElementById("out-raw").textContent = JSON.stringify(body, null, 2);
      resultEl.hidden = false;
    } catch (err) {
      showError(err.message || String(err));
    } finally {
      submitBtn.disabled = false;
    }
  });

  fillDemoBtn.addEventListener("click", fillDemo);
  fillDemo();
  checkApi();
})();
