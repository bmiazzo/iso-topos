# Real Global Datasets: WorldClim Antarctica Elevation Zeroing, GLiM Archives & Planetary PDS Grids

- **Date:** 2026-11-15
- **Area / Tags:** `etl`, `earth-data`, `moon-data`, `mars-data`, `nodata`, `pds`

## What Surprised Us
1. **WorldClim v2.1 `wc2.1_10m_elev.zip` zeros Antarctica (`0 m` across `-90°..-60°`)**, whereas `wc2.1_10m_bio.zip` (`BIO1`) preserves true Antarctic interior temperatures down to `-54.7 °C` and encodes ocean nodata with a `-3.4e38` float32 sentinel that triggers a `tifffile` `GDAL_NODATA` cast warning.
2. **Earth crustal magnetics (`EMAG2v3`) has three critical traps:**
   - NOAA/NCEI's `EMAG2_V3_SeaLevel_DataTiff.tif` (~88.6 MB) is actually an **8-bit RGB shaded visualization (`(5313, 10630, 3) uint8`)**, NOT numeric nanoTeslas.
   - `SeaLevel_tiff.tif` (~239.6 MB float32) covers oceans at sea level (`-3.4e38` nodata across major continental interiors!), whereas **`EMAG2_V3_UpCont_DataTiff.tif`** (~239.6 MB float32) provides continuous global land + ocean 4 km upward-continued coverage (`0..360°` East via `ModelTiepointTag`!).
   - Both real float EMAG2v3 rasters encode missing track gaps with `-99999.0` / `99999.0` / `-3.4e38` sentinels alongside real crustal peaks (`> 1,200 nT` near Kursk / Bangui).
3. **GLiM v1.0 0.5° global lithology (`Zenodo 3245551`) is distributed as an ESRI ASCII grid (`glim_wgs84_0point5deg.txt.asc`) inside a small 39 KB ZIP**, NOT a `.tif` raster (which lives at a separate Zenodo record or fails URL guesses), while Obu et al. (2019) permafrost (`25 km` Polar Stereographic NetCDF) stores explicit 2D `latitude` and `longitude` coordinate datasets inside HDF5 so it can be regridded directly without needing `pyproj`.
4. **Lunar & Martian PDS3 datasets require careful coordinate/unit parsing:**
   - LRO Diviner RDR gridded products (`dgdr_ra_avg_cyl_032_img.img`, `dgdr_st_avg_cyl_032_img.img`) only cover `-60°..+60°` latitude at `32 ppd` (`0°..360°` East longitude).
   - LRO LOLA `LDSM_16.LBL` specifies `WESTERNMOST_LONGITUDE = 360`, `EASTERNMOST_LONGITUDE = 0`, and `CENTER_LONGITUDE = 180` — a `0°..360°` East grid, NOT `-180°..+180°`; failing to pass `lon_min=0, lon_max=360` with `lon_0_360=True` introduces a `180°` shift.
   - Lunar Prospector GRS `lpgrs_high1_elem_abundance_2deg.tab` reports oxides (`W_AL2O3`, `W_FEO`, `W_TIO2`) as **weight fractions (`g/g`)** rather than `wt%`, and uses equal-area longitudinal bins near the poles (`±90°`).

## Why It Matters
- Relying on WorldClim elevation alone flattens the East Antarctic Ice Sheet to sea level (`0 m`), destroying polar Mars/icy analog elevations.
- Unmasked `EMAG2v3` `-99999.0` or WorldClim `-3.4e38` nodata values corrupt cell averages and auto-contrast stretches across the entire globe unless filtered before resampling and gap-filled with provenance tracking.
- Treating `-60°..+60°` planetary rasters as global `-90°..+90°` grids shifts latitudes by 30° unless PDS `MAXIMUM_LATITUDE` / `MINIMUM_LATITUDE` bounds are read directly from `.lbl` headers.

## Rule of Thumb / What To Do Instead
- Always check GeoTIFF `dtype`, `SamplesPerPixel`, and `SampleFormat` explicitly (especially NOAA `SeaLevel_tiff.tif` `float32` vs `EMAG2_V3_SeaLevel_DataTiff.tif` `uint8` RGB!).
- Always use **NOAA ETOPO2v2c** (`ETOPO2v2c_i2_LSB.zip`, true `-90°..+90°`) for global elevation & slope relief; filter `abs(arr) > 1e15` on WorldClim float32 GeoTIFFs and `-99999` / `99999` / `NaN` on EMAG2v3.
- Parse NASA PDS3 `.lbl` keywords (`LINES`, `LINE_SAMPLES`, `MAP_RESOLUTION`, `MINIMUM_LATITUDE`, `MAXIMUM_LATITUDE`, `SCALING_FACTOR`, `OFFSET`, `SAMPLE_TYPE`) dynamically rather than hardcoding image dimensions or global bounds.
- Track every spatially filled gap in `EarthSite.interpolated_parameters` (`src/isotopos/core/models.py`) so scientists see which values came from direct open-grid observation vs. spatial gap filling.

## References
- [`earth_datasets.py`](../src/isotopos/etl/sources/earth_datasets.py)
- [`planetary_datasets.py`](../src/isotopos/etl/sources/planetary_datasets.py)
- [`raster_readers.py`](../src/isotopos/etl/sources/raster_readers.py)
- [`DEC-011`](../decisions/DECISIONS.md)
