(() => {
  "use strict";

  const root = document.getElementById("series-viewer");
  if (!root) return;

  const syncToggle = document.getElementById("sync-viewers");
  const paneElements = [...root.querySelectorAll(".viewer-pane")];
  let activePane = 0;
  let syncing = false;

  const panes = paneElements.map((element, paneIndex) => {
    const assets = [...element.querySelectorAll(".asset-list [data-asset-id]")].map((item) => item.dataset.assetId);
    const image = element.querySelector(".slice-image");
    const loading = element.querySelector(".slice-loading");
    const slider = element.querySelector(".frame-slider");
    const current = element.querySelector(".frame-counter b");
    const previous = element.querySelector(".previous-frame");
    const next = element.querySelector(".next-frame");
    const stage = element.querySelector(".slice-stage");
    const pane = { element, assets, image, loading, slider, current, previous, next, stage, index: 0 };

    function setLocalFrame(index, source = "local") {
      if (!assets.length) {
        loading.textContent = "当前 Series 没有可浏览帧";
        slider.disabled = true;
        previous.disabled = true;
        next.disabled = true;
        return;
      }
      const bounded = Math.max(0, Math.min(index, assets.length - 1));
      pane.index = bounded;
      slider.value = String(bounded + 1);
      current.textContent = String(bounded + 1);
      previous.disabled = bounded === 0;
      next.disabled = bounded === assets.length - 1;
      loading.hidden = false;
      image.src = `/media/${encodeURIComponent(assets[bounded])}`;
      preloadAround(assets, bounded);

      if (source === "local" && syncToggle?.checked && panes.length > 1 && !syncing) {
        syncing = true;
        const ratio = assets.length <= 1 ? 0 : bounded / (assets.length - 1);
        panes.forEach((other, otherIndex) => {
          if (otherIndex === paneIndex || !other.assets.length) return;
          const target = Math.round(ratio * Math.max(0, other.assets.length - 1));
          other.setFrame(target, "sync");
        });
        syncing = false;
      }
    }

    pane.setFrame = setLocalFrame;
    slider.addEventListener("input", () => setLocalFrame(Number(slider.value) - 1));
    previous.addEventListener("click", () => setLocalFrame(pane.index - 1));
    next.addEventListener("click", () => setLocalFrame(pane.index + 1));
    stage.addEventListener("focus", () => { activePane = paneIndex; });
    stage.addEventListener("pointerdown", () => { activePane = paneIndex; });
    image.addEventListener("load", () => { loading.hidden = true; });
    image.addEventListener("error", () => {
      loading.hidden = false;
      loading.textContent = "切片加载失败";
    });
    return pane;
  });

  function preloadAround(assets, index) {
    [-2, -1, 1, 2].forEach((offset) => {
      const asset = assets[index + offset];
      if (!asset) return;
      const image = new Image();
      image.src = `/media/${encodeURIComponent(asset)}`;
    });
  }

  function alignPanes() {
    if (!syncToggle?.checked || panes.length < 2) return;
    const source = panes[activePane] || panes[0];
    const ratio = source.assets.length <= 1 ? 0 : source.index / (source.assets.length - 1);
    panes.forEach((pane, index) => {
      if (index === activePane || !pane.assets.length) return;
      pane.setFrame(Math.round(ratio * Math.max(0, pane.assets.length - 1)), "sync");
    });
  }

  syncToggle?.addEventListener("change", alignPanes);
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    const pane = panes[activePane] || panes[0];
    if (!pane) return;
    event.preventDefault();
    if (event.key === "Home") pane.setFrame(0);
    else if (event.key === "End") pane.setFrame(pane.assets.length - 1);
    else pane.setFrame(pane.index + (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1));
  });

  panes.forEach((pane) => pane.setFrame(0, "initial"));
})();
