# CSS Inline Custom Properties vs. Collapsed Grid Tracks & CesiumJS 2× Label Supersampling

- **Date:** 2026-11-15
- **Area / Tags:** `frontend`, `css-grid`, `cesiumjs`, `hidpi`, `labels`, `ui`

## What Surprised Us
1. **Inline CSS Custom Properties Override Collapsed Class Rules:** Setting `workspaceEl.style.setProperty("--left-width", "340px")` from a JS resize controller places `--left-width` in the element's inline `style` attribute. When a `.left-collapsed` class was toggled on the same `.workspace` element with `.workspace.left-collapsed { --left-width: 0px; }`, the inline style won the CSS cascade. Because `.workspace.left-collapsed .left-panel` set `opacity: 0`, the sidebar disappeared visually while its `340px` grid track remained open, leaving a solid black bar on the side of the screen.
2. **CesiumJS `useBrowserRecommendedResolution: true` and `11px` `LabelCollection` Glyphs:** Passing `useBrowserRecommendedResolution: true` to `Cesium.Viewer` ignores `window.devicePixelRatio` on HiDPI displays. Furthermore, `Cesium.LabelCollection` rasterizes each character into an internal 2D `<canvas>` texture atlas at the exact pixel size in `font`. Using `font: "600 11px ..."` with `scale: 1.0` and `outlineWidth: 3` produces a tiny, low-texel-density bitmap where the 3px stroke chokes and pixelates the glyphs.

## Why It Matters
- Users collapsing a sidebar to inspect the 3D globe full-screen saw large black bars on the left and right edges instead of an expanded globe.
- 3D tags on the Earth, Moon, and Mars globes appeared blurry/pixelated and overlapped at global zoom.

## Rule of Thumb / What To Do Instead
- **Separate Size State Variables from Track Layout Variables:** Store JS-driven custom widths in `--left-width` / `--right-width`, bind `grid-template-columns` to derived `--left-track: var(--left-width)` / `--right-track: var(--right-width)`, and collapse via `.left-collapsed { --left-track: 0px !important; }`. That way collapsing always reaches `0px` and re-expanding automatically restores the user's custom width.
- **Supersample CesiumJS WebGL Labels & Billboards:** Set `useBrowserRecommendedResolution: false` and `viewer.resolutionScale = Math.min(window.devicePixelRatio || 1, 2.25)`, rasterize `LabelCollection` fonts at `2×` size (`22px–25px`) with `scale: 0.48–0.56` and `showBackground: true`, and render canvas pin billboards at `pixelRatio = 2.5` with explicit logical `width`/`height`.

## References
- [`src/isotopos/static/styles/layout.css`](../src/isotopos/static/styles/layout.css)
- [`src/isotopos/static/js/components/cesium_helpers.js`](../src/isotopos/static/js/components/cesium_helpers.js)
- `DEC-019` in [`decisions/DECISIONS.md`](../decisions/DECISIONS.md)
