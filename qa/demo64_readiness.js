// Acceptance instrumentation only. Installed before navigation; never reads pixels.
(() => {
  const states = new WeakMap(); let sequence = 0;
  const state = el => { if (!states.has(el)) states.set(el, {}); return states.get(el); };
  document.addEventListener('CORNERSTONE_STACK_NEW_IMAGE', e => {
    const s = state(e.target); s.imageId = e.detail.imageId; s.renderedImageId = null;
  }, true);
  document.addEventListener('CORNERSTONE_IMAGE_RENDERED', e => {
    const s = state(e.target); s.renderedImageId = s.imageId; s.renderSequence = ++sequence;
    s.engineId = e.detail.renderingEngineId; s.viewportId = e.detail.viewportId;
  }, true);
  const clear = CanvasRenderingContext2D.prototype.clearRect;
  CanvasRenderingContext2D.prototype.clearRect = function(...args) {
    const value = clear.apply(this, args);
    if (this.canvas.getAttribute('aria-label') === '模型响应叠加图层') {
      const el = this.canvas.parentElement?.querySelector('.cornerstone-viewport');
      if (el) state(el).overlay = null;
    }
    return value;
  };
  const original = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function(...args) {
    const value = original.apply(this, args);
    if (this.canvas.getAttribute('aria-label') === '模型响应叠加图层') {
      const el = this.canvas.parentElement?.querySelector('.cornerstone-viewport');
      if (el) state(el).overlay = { source: args[0].src, width: args[0].naturalWidth,
        height: args[0].naturalHeight, sequence: ++sequence, imageId: state(el).renderedImageId };
    }
    return value;
  };
  const visible = el => !!el && el.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}) &&
    el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
  window.__epiTechnicalProbe = async expected => {
    try {
      const mod = await import(expected.coreUrl); const core = mod.getRenderingEngines ? mod : mod.t;
      const el = document.querySelector('.cornerstone-viewport'); const s = states.get(el);
      const engine = core.getRenderingEngines().find(x => x.id === s?.engineId);
      const viewport = engine?.getViewport(s?.viewportId);
      const image = viewport?.getCornerstoneImage(); const current = viewport?.getCurrentImageId();
      const overlay = document.querySelector('.cornerstone-overlay');
      const errors = [...document.querySelectorAll('.notice-error')].filter(visible).length;
      const checks = {
        location: location.pathname === expected.pathname,
        current_render: !!current && s?.renderedImageId === current && s?.imageId === current && s?.renderSequence > (expected.afterSequence || 0),
        decoded: !!image && image.columns === expected.width && image.rows === expected.height,
        rendered_status: viewport?.viewportStatus === 'rendered',
        canvas_visible: visible(el) && visible(viewport?.canvas) && viewport.canvas.width > 0 && viewport.canvas.height > 0,
        no_error: errors === 0,
        asset: !expected.assetUrl || (visible(overlay) && s?.overlay?.source === expected.assetUrl &&
          s.overlay.width === expected.assetSize && s.overlay.height === expected.assetSize &&
          s.overlay.imageId === current && s.overlay.sequence > (expected.afterOverlaySequence || 0)),
      };
      return {ready:Object.values(checks).every(Boolean), checks,
        renderSequence:s?.renderSequence || 0, overlaySequence:s?.overlay?.sequence || 0};
    } catch { return {ready:false, checks:{inspection:false},renderSequence:0,overlaySequence:0}; }
  };
})();
