(() => {
  "use strict";

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const filterButtons = [...document.querySelectorAll("[data-admin-filter]")];
  const caseRows = [...document.querySelectorAll(".admin-case-row")];
  const finalForm = document.getElementById("admin-final-form");

  function showToast(message, type = "info") {
    const region = document.getElementById("toast-region");
    if (!region) return;
    const toast = document.createElement("div");
    toast.className = `toast${type === "error" ? " toast-error" : ""}`;
    toast.textContent = message;
    region.append(toast);
    window.setTimeout(() => toast.remove(), 4200);
  }

  filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const filter = button.dataset.adminFilter;
      filterButtons.forEach((item) => item.classList.toggle("active", item === button));
      caseRows.forEach((row) => {
        row.hidden = filter !== "ALL"
          && !(filter === "DEFER" && row.dataset.hasDefer === "true")
          && row.dataset.status !== filter;
      });
    });
  });

  async function submitFinalDecision(event) {
    event.preventDefault();
    const selected = finalForm.querySelector('input[name="final-decision"]:checked');
    const reason = finalForm.elements.reason.value.trim();
    const imageReviewed = finalForm.elements.image_evidence_reviewed.checked;
    const metadataReviewed = finalForm.elements.metadata_evidence_reviewed.checked;
    if (!selected) return showToast("请选择最终决定。", "error");
    if (reason.length < 20) return showToast("最终理由至少需要 20 个字符。", "error");
    if (!imageReviewed || !metadataReviewed) return showToast("定稿前必须确认已查看图像和 metadata 证据。", "error");

    const submit = finalForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    submit.textContent = "正在定稿...";
    try {
      const response = await fetch(finalForm.dataset.submitUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
        body: JSON.stringify({
          version: finalForm.dataset.version ? Number(finalForm.dataset.version) : null,
          decision: selected.value,
          selected_series_uid: selected.dataset.seriesUid || "",
          reason,
          image_evidence_reviewed: imageReviewed,
          metadata_evidence_reviewed: metadataReviewed,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || data.error || `定稿失败 (${response.status})`);
      finalForm.dataset.existing = "true";
      if (data.final_decision?.version) finalForm.dataset.version = String(data.final_decision.version);
      submit.textContent = "最终记录已保存";
      showToast("最终决定已记录。", "info");
    } catch (error) {
      submit.disabled = false;
      submit.textContent = finalForm.dataset.existing === "true" ? "更新最终决定" : "确认最终决定";
      showToast(error.message || "定稿失败。", "error");
    }
  }

  finalForm?.addEventListener("submit", submitFinalDecision);
})();
