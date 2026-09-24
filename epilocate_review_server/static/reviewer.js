(() => {
  "use strict";

  const form = document.getElementById("review-form");
  if (!form) return;

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const saveIndicator = document.getElementById("save-indicator");
  const draftState = document.getElementById("draft-state");
  const reasonField = document.getElementById("reason");
  const recommendationBox = document.getElementById("recommendation");
  const recommendationText = document.getElementById("recommendation-text");
  const adoptButton = document.getElementById("adopt-recommendation");
  const submitButton = document.getElementById("submit-review");
  const reopenButton = document.getElementById("reopen-review");
  const isReadOnly = form.dataset.readOnly === "true";
  const candidateInputs = [...document.querySelectorAll('input[name="decision-picker"][data-series-uid]')];
  let currentRecommendation = normalizeRecommendation({
    decision: recommendationBox?.dataset.decision,
    selected_series_uid: recommendationBox?.dataset.seriesUid,
    reason: recommendationBox?.dataset.reason,
    label: recommendationText?.textContent,
  });
  let saveTimer = 0;
  let requestSerial = 0;
  let saving = false;
  let saveAgain = false;
  let conflict = false;

  function normalizeRecommendation(value) {
    if (!value || !value.decision || value.decision === "PENDING" || value.complete === false) return null;
    return {
      decision: value.decision || "",
      selected_series_uid: value.selected_series_uid || "",
      reason: value.reason || "",
      label: value.label || value.text || recommendationLabel(value.decision, value.selected_series_uid),
    };
  }

  function recommendationLabel(decision, selectedUid) {
    if (decision === "DEFER") return "建议 DEFER：证据不足或方向不一致";
    if (decision === "EXCLUDE_PATIENT") return "建议排除：存在明确的不适用证据";
    const index = candidateInputs.findIndex((input) => input.dataset.seriesUid === selectedUid);
    if (decision === "INCLUDE_REVIEW_SERIES") return "建议纳入这套 Series";
    return `建议选择候选 ${index === 1 ? "B" : "A"}`;
  }

  function showToast(message, type = "info") {
    const region = document.getElementById("toast-region");
    if (!region) return;
    const toast = document.createElement("div");
    toast.className = `toast${type === "error" ? " toast-error" : ""}`;
    toast.textContent = message;
    region.append(toast);
    window.setTimeout(() => toast.remove(), 4200);
  }

  function setSaveState(state, text) {
    if (!saveIndicator) return;
    saveIndicator.dataset.state = state;
    const label = saveIndicator.querySelector("span");
    if (label) label.textContent = text;
  }

  function observations() {
    const values = {};
    form.querySelectorAll("[data-observation]").forEach((row) => {
      const selected = row.querySelector('input[type="radio"]:checked');
      if (selected) values[row.dataset.observation] = selected.value;
    });
    return values;
  }

  function selectedDecision() {
    const selected = document.querySelector('input[name="decision-picker"]:checked');
    return {
      decision: selected?.value || "PENDING",
      selected_series_uid: selected?.dataset.seriesUid || "",
    };
  }

  function payload() {
    const selection = selectedDecision();
    return {
      version: Number(form.dataset.version || 0),
      observations: observations(),
      decision: selection.decision,
      selected_series_uid: selection.selected_series_uid,
      reason: reasonField?.value.trim() || "",
      image_evidence_reviewed: Boolean(form.elements.image_evidence_reviewed?.checked),
      metadata_evidence_reviewed: Boolean(form.elements.metadata_evidence_reviewed?.checked),
    };
  }

  function tieRecommendation(values) {
    const keys = ["texture", "noise", "artifact", "coverage"];
    const complete = keys.filter((key) => values[key]).length;
    if (complete < keys.length) return { pending: `已完成 ${complete} / 4 项，请继续填写。` };

    const a = keys.filter((key) => values[key] === "A");
    const b = keys.filter((key) => values[key] === "B");
    if (a.length >= 2 && b.length === 0) return tieWinner("A", a, candidateInputs[0]?.dataset.seriesUid || "");
    if (b.length >= 2 && a.length === 0) return tieWinner("B", b, candidateInputs[1]?.dataset.seriesUid || "");

    const duplicate = form.dataset.caseId === "TIE-012" && a.length === 0 && b.length === 0;
    return {
      decision: "DEFER",
      selected_series_uid: "",
      label: duplicate ? "建议 DEFER：两套可能为重复 Series" : "建议 DEFER：证据不足或方向不一致",
      reason: duplicate
        ? "两套候选的层厚、像素间距、覆盖和切片数量一致，图像表现也高度相似，目前疑似重复 Series；在没有进一步比较几何位置、时间和对应像素前，现有证据不足以支持选择，因此暂缓决定。"
        : "不同观察维度对候选 Series 的支持方向不一致，或现有图像与 metadata 证据不足以形成稳定、可重复的人工选择依据，因此暂缓决定。",
    };
  }

  function tieWinner(alias, supportedKeys, uid) {
    const labels = {
      texture: "肺实质纹理和细小结构显示更清楚",
      noise: "图像噪声相对更少",
      artifact: "运动、条纹或其他明显伪影相对更少",
      coverage: "胸部解剖覆盖更完整",
    };
    const parts = supportedKeys.map((key) => `候选 ${alias} 的${labels[key]}`);
    return {
      decision: "SELECT_ONE_CANDIDATE",
      selected_series_uid: uid,
      label: `建议选择候选 ${alias}`,
      reason: `${parts.join("；")}。以上差异来自可复核的图像与 metadata 证据，能够形成稳定的技术选择依据，因此选择候选 ${alias} 作为本研究输入。`,
    };
  }

  function diagnosticRecommendation(values) {
    const keys = ["diag_coverage", "diag_artifact", "diag_use"];
    const complete = keys.filter((key) => values[key]).length;
    if (complete < keys.length) return { pending: `已完成 ${complete} / 3 项，请继续填写。` };
    const uid = candidateInputs[0]?.dataset.seriesUid || "";
    if (keys.every((key) => values[key] === "YES")) {
      return {
        decision: "INCLUDE_REVIEW_SERIES",
        selected_series_uid: uid,
        label: "建议纳入这套 Series",
        reason: "完整 Series 的胸部解剖覆盖基本完整，图像中的运动、条纹或其他明显伪影处于可接受范围；结合 metadata，可确认其具备作为本研究诊断性胸部 CT 输入的基本条件，因此纳入该 Series。",
      };
    }
    if (values.diag_coverage === "NO" || values.diag_artifact === "NO" || values.diag_use === "NO") {
      return {
        decision: "EXCLUDE_PATIENT",
        selected_series_uid: "",
        label: "建议排除患者",
        reason: "完整 Series 存在胸部覆盖不足、明显伪影或整体用途不符合研究输入要求的证据，因此该 Series 不适合作为本研究的诊断性胸部 CT 输入，排除该患者。",
      };
    }
    return {
      decision: "DEFER",
      selected_series_uid: "",
      label: "建议 DEFER：仍有项目无法确认",
      reason: "当前复核中仍存在无法确认的图像或 metadata 证据，尚不能可靠判断该 Series 是否适合作为诊断性胸部 CT 研究输入，因此暂缓决定并交由更有经验的复核者确认。",
    };
  }

  function updateRecommendation(value = null) {
    const preview = normalizeRecommendation(value) || (form.dataset.caseType === "technical_tie"
      ? tieRecommendation(observations())
      : diagnosticRecommendation(observations()));

    if (preview.pending) {
      currentRecommendation = null;
      recommendationText.textContent = preview.pending;
      adoptButton.disabled = true;
      return;
    }
    currentRecommendation = preview;
    recommendationText.textContent = preview.label;
    adoptButton.disabled = isReadOnly;
    recommendationBox.dataset.decision = preview.decision;
    recommendationBox.dataset.seriesUid = preview.selected_series_uid;
    recommendationBox.dataset.reason = preview.reason;
  }

  function chooseRecommendation() {
    const decision = recommendationBox?.dataset.decision || "";
    const selectedUid = recommendationBox?.dataset.seriesUid || "";
    if (!decision || decision === "PENDING") return;
    const target = [...document.querySelectorAll('input[name="decision-picker"]')].find((input) => (
      input.value === decision && (input.dataset.seriesUid || "") === selectedUid
    ));
    if (!target) {
      showToast("当前建议的 Series 映射失效，请刷新页面。", "error");
      return;
    }
    target.checked = true;
    reasonField.value = recommendationBox?.dataset.reason || "";
    reasonField.dataset.autoReason = "true";
    reasonField.dataset.autoDecision = decision;
    reasonField.dataset.autoSeriesUid = selectedUid;
    markDirty();
    scheduleSave();
    showToast("建议已填入草稿，请核对后再提交。", "info");
  }

  function clearMismatchedAutoReason() {
    if (reasonField.dataset.autoReason !== "true") return;
    const selected = selectedDecision();
    if (
      selected.decision !== reasonField.dataset.autoDecision
      || selected.selected_series_uid !== (reasonField.dataset.autoSeriesUid || "")
    ) {
      reasonField.value = "";
      delete reasonField.dataset.autoReason;
      delete reasonField.dataset.autoDecision;
      delete reasonField.dataset.autoSeriesUid;
    }
  }

  function markDirty() {
    if (!conflict) setSaveState("dirty", "有未保存修改");
  }

  function scheduleSave() {
    if (isReadOnly || conflict) return;
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => saveDraft(), 750);
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        ...(options.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.detail || data.error || `请求失败 (${response.status})`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  async function saveDraft() {
    if (isReadOnly || conflict) return;
    if (saving) {
      saveAgain = true;
      return;
    }
    saving = true;
    saveAgain = false;
    const serial = ++requestSerial;
    setSaveState("saving", "正在保存草稿...");
    try {
      const result = await requestJson(form.dataset.draftUrl, {
        method: "PATCH",
        body: JSON.stringify(payload()),
      });
      if (serial !== requestSerial) return;
      const version = Number(result.version ?? result.review?.version ?? form.dataset.version);
      form.dataset.version = String(version);
      form.elements.version.value = String(version);
      if (draftState) draftState.textContent = `草稿版本 ${version}`;
      if (result.recommendation) updateRecommendation(result.recommendation);
      setSaveState("saved", "草稿已保存");
    } catch (error) {
      if (error.status === 409) {
        conflict = true;
        setSaveState("error", "版本冲突，请刷新页面");
        showToast("另一标签页已更新本例。请刷新页面后继续，当前页面不会覆盖新版本。", "error");
      } else {
        setSaveState("error", "草稿保存失败");
        showToast(error.message || "草稿保存失败，请检查网络后重试。", "error");
      }
    } finally {
      saving = false;
      if (saveAgain && !conflict) saveDraft();
    }
  }

  function validateForSubmit(data) {
    if (!data.decision || data.decision === "PENDING") return "请选择最终决定。";
    if (["SELECT_ONE_CANDIDATE", "INCLUDE_REVIEW_SERIES"].includes(data.decision) && !data.selected_series_uid) return "选择候选时必须对应一套 Series。";
    if (data.reason.length < 20) return "请填写至少 20 个字符的可复核理由。";
    if (!data.image_evidence_reviewed || !data.metadata_evidence_reviewed) return "提交前必须确认已查看图像和 metadata 证据。";
    return "";
  }

  async function submitReview(event) {
    event.preventDefault();
    if (isReadOnly || conflict) return;
    window.clearTimeout(saveTimer);
    if (saving) {
      saveAgain = true;
      showToast("草稿正在保存，请稍候再提交。", "info");
      return;
    }
    const data = payload();
    const validationError = validateForSubmit(data);
    if (validationError) {
      showToast(validationError, "error");
      return;
    }
    submitButton.disabled = true;
    submitButton.textContent = "正在提交...";
    try {
      const result = await requestJson(form.dataset.submitUrl, {
        method: "POST",
        body: JSON.stringify(data),
      });
      const version = Number(result.version ?? result.review?.version ?? form.dataset.version);
      form.dataset.version = String(version);
      setSaveState("saved", "已提交");
      form.querySelectorAll("input, textarea, button").forEach((control) => { control.disabled = true; });
      candidateInputs.forEach((control) => { control.disabled = true; });
      submitButton.textContent = "本例已提交";
      showToast("本例已提交。", "info");
    } catch (error) {
      submitButton.disabled = false;
      submitButton.textContent = "确认并提交本例";
      if (error.status === 409) conflict = true;
      setSaveState("error", error.status === 409 ? "版本冲突，请刷新页面" : "提交失败");
      showToast(error.message || "提交失败。", "error");
    }
  }

  async function reopenReview() {
    reopenButton.disabled = true;
    try {
      await requestJson(form.dataset.reopenUrl, { method: "POST", body: "{}" });
      window.location.reload();
    } catch (error) {
      reopenButton.disabled = false;
      showToast(error.message || "无法重新打开本例。", "error");
    }
  }

  form.addEventListener("change", (event) => {
    if (event.target.matches('[name="decision-picker"]')) clearMismatchedAutoReason();
    if (event.target.closest("[data-observation]")) updateRecommendation();
    markDirty();
    scheduleSave();
  });
  form.addEventListener("input", (event) => {
    if (event.target === reasonField) delete reasonField.dataset.autoReason;
    markDirty();
    scheduleSave();
  });
  candidateInputs.forEach((input) => input.addEventListener("change", () => {
    clearMismatchedAutoReason();
    markDirty();
    scheduleSave();
  }));
  form.addEventListener("submit", submitReview);
  adoptButton?.addEventListener("click", chooseRecommendation);
  reopenButton?.addEventListener("click", reopenReview);
  window.addEventListener("beforeunload", (event) => {
    if (saveIndicator?.dataset.state === "dirty" || saving) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  updateRecommendation(currentRecommendation);
})();
