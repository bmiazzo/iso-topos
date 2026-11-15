# Obu Fill-Value Coordinates, Polar Bin Voids & MODIS Dimension Scales

- **Date:** 2026-11-15
- **Area / Tags:** `etl`, `earth-data`, `permafrost`, `modis`, `python314`

## What Surprised Us
1. **Finite `1e32` `_FillValue` coordinates in Obu et al. (2019):** `obu_permafrost_25km.nc` stores `_FillValue = 1e32` as a finite `float32` in `latitude` and `longitude`. Filtering only with `np.isfinite(lats)` lets `1e32` slip through when paired with a borderline/valid `PerProb`, which then triggers `np.clip(np.floor((90 - 1e32) / 0.5), 0, nlat - 1)` — raising a NumPy cast `RuntimeWarning` and silently writing permafrost values into North Pole row `0` (`89.75°N`).
2. **High-latitude `25 km -> 0.5°` bin voids cannot use global gap-fill:** Above `~63°N`, `0.5°` longitude spacing (`< 25 km`) leaves empty interior `NaN` cells inside the Obu polar grid. Calling `fill_raster_gaps_with_mask` there is dangerous because its row/global median fallback floods oceans and the Southern Hemisphere with Northern permafrost; meanwhile `np.roll` shifts across `axis=0` wrap North Pole rows onto Antarctica unless polar rows are zeroed (`row 0` when `dr=1`, `row nrows-1` when `dr=-1`).
3. **Zeroed MODIS dimension scales:** `MODIS_Land_Cover_Climatology.CMG005.nc` stores `latitude` as an all-zero NetCDF dimension-scale stub (`np.zeros(3600)`) alongside transposed `(lon, lat)` data and `landcover_PFT=127` / water=`0` coastline pixels.
4. **Aridity raster shape vs. extent:** CGIAR/WorldClim Aridity rasters appear in both `-90..90` (`1:2` aspect, `3600x7200`) and `-60..90` (`5:12` aspect, `3000x7200`) variants; hardcoding `nrows < 3200 -> -60°` misclassifies smaller test/resampled full-globe GeoTIFFs unless `ModelPixelScaleTag` / `ModelTiepointTag` or `nrows / ncols < 0.46` is inspected.

## Why It Matters
Silent coordinate clamping and polar-wrap artifacts inject false permafrost signals into North Pole or Antarctic cells without failing fast, while hardcoded pixel dimensions break fast deterministic unit fixtures (`DR-4`).

## Rule of Thumb / What To Do Instead
- Always bound-check Earth grid coordinates (`-90 <= lat <= 90`, `-180 <= lon <= 360`) before binning/clipping, not just `np.isfinite`.
- Heal polar regridding voids using bounded local 8-neighbor diffusion (`_heal_local_grid_pinholes`) with latitude pole-boundary masking (`dr == 1` zeros `row 0`; `dr == -1` zeros `row -1`), never row/global fallback on hemisphere-restricted datasets.
- Infer GeoTIFF southern bounds from GeoTIFF tie/scale tags or aspect ratio rather than pixel row thresholds alone, and validate `lat_vec[0] < lat_vec[-1]` on non-degenerate HDF5 coordinate vectors.

## References
- [src/isotopos/etl/sources/earth_datasets.py](../src/isotopos/etl/sources/earth_datasets.py)
- [tests/unit/test_open_dataset_sources.py](../tests/unit/test_open_dataset_sources.py)
