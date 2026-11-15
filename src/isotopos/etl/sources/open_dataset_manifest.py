"""Manifest of verified auth-free open scientific datasets fetched into data/raw/."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetAsset:
    """Declarative specification for one downloadable auth-free scientific file."""

    key: str
    scope: str  # "earth" | "moon" | "mars" | "shared"
    url: str
    rel_path: str
    description: str
    min_bytes: int = 512

    def resolve(self, raw_dir: Path) -> Path:
        """Resolve local target path inside raw_dir."""
        return raw_dir / self.rel_path


OPEN_DATASET_MANIFEST: tuple[DatasetAsset, ...] = (
    # --- Shared / Administrative boundaries ---
    DatasetAsset(
        key="ne_countries",
        scope="earth",
        url="https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson",
        rel_path="ne_50m_admin_0_countries.geojson",
        description="Natural Earth 1:50m Admin-0 Countries GeoJSON",
        min_bytes=500_000,
    ),
    DatasetAsset(
        key="ne_antarctic_ice_shelves",
        scope="earth",
        url="https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_antarctic_ice_shelves_polys.geojson",
        rel_path="ne_50m_antarctic_ice_shelves_polys.geojson",
        description="Natural Earth 1:50m Antarctic Ice Shelves Polygons GeoJSON",
        min_bytes=50_000,
    ),
    # --- Earth global physical, climate, magnetic, lithology & cryosphere datasets ---
    DatasetAsset(
        key="emag2_sealevel",
        scope="earth",
        url="https://www.ngdc.noaa.gov/geomag/data/EMAG2/EMAG2_V3_UpCont_DataTiff.tif",
        rel_path="earth/emag2_v3_upcont.tif",
        description="NOAA NCEI EMAG2v3 Earth Magnetic Anomaly Grid float32 4km upward-continued GeoTIFF (global land+ocean, nT, 2 arc-min)",
        min_bytes=200_000_000,
    ),
    DatasetAsset(
        key="etopo2_global",
        scope="earth",
        url="https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2/ETOPO2v2-2006/ETOPO2v2c/raw_binary/ETOPO2v2c_i2_LSB.zip",
        rel_path="earth/etopo2v2c_i2_lsb.zip",
        description="NOAA ETOPO2v2c 2-arc-min global relief (includes Antarctica -90..+90)",
        min_bytes=20_000_000,
    ),
    DatasetAsset(
        key="worldclim_bio",
        scope="earth",
        url="https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_bio.zip",
        rel_path="earth/wc2.1_10m_bio.zip",
        description="WorldClim v2.1 10-arc-min bioclimatic GeoTIFFs (BIO1, BIO2, BIO4, BIO12)",
        min_bytes=30_000_000,
    ),
    DatasetAsset(
        key="worldclim_srad",
        scope="earth",
        url="https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_srad.zip",
        rel_path="earth/wc2.1_10m_srad.zip",
        description="WorldClim v2.1 10-arc-min monthly solar radiation GeoTIFFs",
        min_bytes=10_000_000,
    ),
    DatasetAsset(
        key="glim_lithology",
        scope="earth",
        url="https://epic.awi.de/id/eprint/31092/1/hartmann-moosdorf_2012.zip",
        rel_path="earth/glim_05deg.zip",
        description="Hartmann & Moosdorf (2012) GLiM v1.0 0.5-deg Global Lithological Map",
        min_bytes=20_000,
    ),
    DatasetAsset(
        key="modis_landcover",
        scope="earth",
        url="https://zenodo.org/api/records/6350821/files/landcover_climatology.zip/content",
        rel_path="earth/modis_landcover.zip",
        description="MODIS MCD12C1 global land cover climatology (Zenodo 6350821)",
        min_bytes=5_000_000,
    ),
    DatasetAsset(
        key="global_aridity",
        scope="earth",
        url="https://zenodo.org/api/records/10074189/files/2017.tif/content",
        rel_path="earth/global_aridity_2017.tif",
        description="Global Aridity Index (P/PET) GeoTIFF (Zenodo 10074189)",
        min_bytes=10_000_000,
    ),
    DatasetAsset(
        key="obu_permafrost",
        scope="earth",
        url="https://store.pangaea.de/Publications/ObuJ-etal_2018/UiO_PEX_5.0_20181127_2000_2016_25km.nc",
        rel_path="earth/obu_permafrost_25km.nc",
        description="Obu et al. (2019) Northern Hemisphere 25km Permafrost & MAGT NetCDF",
        min_bytes=10_000_000,
    ),
    # --- Moon NASA PDS & SH magnetic datasets ---
    DatasetAsset(
        key="lola_ldem_lbl",
        scope="moon",
        url="https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/ldem_4.lbl",
        rel_path="moon/ldem_4.lbl",
        description="LRO LOLA 4ppd DEM PDS3 label",
        min_bytes=1_000,
    ),
    DatasetAsset(
        key="lola_ldem_img",
        scope="moon",
        url="https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/ldem_4.img",
        rel_path="moon/ldem_4.img",
        description="LRO LOLA 4ppd lunar elevation raster",
        min_bytes=1_500_000,
    ),
    DatasetAsset(
        key="lola_ldsm_lbl",
        scope="moon",
        url="https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/ldsm_16.lbl",
        rel_path="moon/ldsm_16.lbl",
        description="LRO LOLA 16ppd slope PDS3 label",
        min_bytes=1_000,
    ),
    DatasetAsset(
        key="lola_ldsm_img",
        scope="moon",
        url="https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/ldsm_16.img",
        rel_path="moon/ldsm_16.img",
        description="LRO LOLA 16ppd lunar bi-directional slope (deg)",
        min_bytes=25_000_000,
    ),
    DatasetAsset(
        key="lola_ldrm_lbl",
        scope="moon",
        url="https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/ldrm_16.lbl",
        rel_path="moon/ldrm_16.lbl",
        description="LRO LOLA 16ppd roughness PDS3 label",
        min_bytes=1_000,
    ),
    DatasetAsset(
        key="lola_ldrm_img",
        scope="moon",
        url="https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/ldrm_16.img",
        rel_path="moon/ldrm_16.img",
        description="LRO LOLA 16ppd lunar surface roughness",
        min_bytes=25_000_000,
    ),
    DatasetAsset(
        key="diviner_ra_lbl",
        scope="moon",
        url="https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gdr_l3/cylindrical/img/dgdr_ra_avg_cyl_032_img.lbl",
        rel_path="moon/dgdr_ra_avg_cyl_032_img.lbl",
        description="LRO Diviner rock abundance PDS3 label",
        min_bytes=1_000,
    ),
    DatasetAsset(
        key="diviner_ra_img",
        scope="moon",
        url="https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gdr_l3/cylindrical/img/dgdr_ra_avg_cyl_032_img.img",
        rel_path="moon/dgdr_ra_avg_cyl_032_img.img",
        description="LRO Diviner 32ppd global rock abundance (-60..+60)",
        min_bytes=60_000_000,
    ),
    DatasetAsset(
        key="diviner_st_lbl",
        scope="moon",
        url="https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gdr_l3/cylindrical/img/dgdr_st_avg_cyl_032_img.lbl",
        rel_path="moon/dgdr_st_avg_cyl_032_img.lbl",
        description="LRO Diviner surface temperature deviation PDS3 label",
        min_bytes=1_000,
    ),
    DatasetAsset(
        key="diviner_st_img",
        scope="moon",
        url="https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gdr_l3/cylindrical/img/dgdr_st_avg_cyl_032_img.img",
        rel_path="moon/dgdr_st_avg_cyl_032_img.img",
        description="LRO Diviner 32ppd regolith nighttime temperature variation (-60..+60)",
        min_bytes=60_000_000,
    ),
    DatasetAsset(
        key="lp_grs_2deg",
        scope="moon",
        url="https://pds-geosciences.wustl.edu/lunar/lp-l-grs-5-elem-abundance-v1/lp_9001/data/lpgrs_high1_elem_abundance_2deg.tab",
        rel_path="moon/lpgrs_high1_elem_abundance_2deg.tab",
        description="Lunar Prospector GRS 2-deg elemental abundance table (FeO, TiO2, Al2O3, SiO2, Neutron)",
        min_bytes=5_000_000,
    ),
    DatasetAsset(
        key="tsunakawa_mag",
        scope="moon",
        url="https://zenodo.org/api/records/3873648/files/T2015_449.sh.gz/content",
        rel_path="moon/T2015_449.sh.gz",
        description="Tsunakawa et al. (2015) degree-449 lunar magnetic spherical harmonic model (Zenodo 3873648)",
        min_bytes=1_000_000,
    ),
    # --- Mars NASA PDS & SH magnetic datasets ---
    DatasetAsset(
        key="mola_megt_lbl",
        scope="mars",
        url="https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg004/megt90n000cb.lbl",
        rel_path="mars/megt90n000cb.lbl",
        description="MGS MOLA 4ppd topography PDS3 label",
        min_bytes=1_000,
    ),
    DatasetAsset(
        key="mola_megt_img",
        scope="mars",
        url="https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg004/megt90n000cb.img",
        rel_path="mars/megt90n000cb.img",
        description="MGS MOLA 4ppd Mars global elevation raster",
        min_bytes=1_500_000,
    ),
    DatasetAsset(
        key="tes_albedo_lbl",
        scope="mars",
        url="https://pds-geosciences.wustl.edu/mgs/mgs-m-tes-special-v1/global_albedo_8ppd.lbl",
        rel_path="mars/global_albedo_8ppd.lbl",
        description="MGS TES 8ppd bolometric albedo PDS3 label",
        min_bytes=500,
    ),
    DatasetAsset(
        key="tes_albedo_img",
        scope="mars",
        url="https://pds-geosciences.wustl.edu/mgs/mgs-m-tes-special-v1/global_albedo_8ppd.img",
        rel_path="mars/global_albedo_8ppd.img",
        description="MGS TES 8ppd bolometric albedo raster",
        min_bytes=10_000_000,
    ),
    DatasetAsset(
        key="tes_ti_lbl",
        scope="mars",
        url="https://pds-geosciences.wustl.edu/mgs/mgs-m-tes-5-timap-v1/mgst_9001/data/global_ti_night_2007.lbl",
        rel_path="mars/global_ti_night_2007.lbl",
        description="MGS TES night thermal inertia PDS3 label",
        min_bytes=500,
    ),
    DatasetAsset(
        key="tes_ti_img",
        scope="mars",
        url="https://pds-geosciences.wustl.edu/mgs/mgs-m-tes-5-timap-v1/mgst_9001/data/global_ti_night_2007.img",
        rel_path="mars/global_ti_night_2007.img",
        description="MGS TES nightside thermal inertia (J/m^2/K/s^0.5)",
        min_bytes=40_000_000,
    ),
    DatasetAsset(
        key="ody_grs_h2o",
        scope="mars",
        url="https://pds-geosciences.wustl.edu/ody/ody-m-grs-5-elements-v1/odgm_xxxx/data/smoothed/h2o_sr_5x5.tab",
        rel_path="mars/h2o_sr_5x5.tab",
        description="Mars Odyssey GRS 5x5 deg H2O weight percent table",
        min_bytes=50_000,
    ),
    DatasetAsset(
        key="ody_grs_fe",
        scope="mars",
        url="https://pds-geosciences.wustl.edu/ody/ody-m-grs-5-elements-v1/odgm_xxxx/data/smoothed/fe_sr_5x5.tab",
        rel_path="mars/fe_sr_5x5.tab",
        description="Mars Odyssey GRS 5x5 deg Fe weight percent table",
        min_bytes=50_000,
    ),
    DatasetAsset(
        key="ody_grs_si",
        scope="mars",
        url="https://pds-geosciences.wustl.edu/ody/ody-m-grs-5-elements-v1/odgm_xxxx/data/smoothed/si_sr_5x5.tab",
        rel_path="mars/si_sr_5x5.tab",
        description="Mars Odyssey GRS 5x5 deg Si weight percent table",
        min_bytes=50_000,
    ),
    DatasetAsset(
        key="ody_grs_cl",
        scope="mars",
        url="https://pds-geosciences.wustl.edu/ody/ody-m-grs-5-elements-v1/odgm_xxxx/data/smoothed/cl_sr_5x5.tab",
        rel_path="mars/cl_sr_5x5.tab",
        description="Mars Odyssey GRS 5x5 deg Cl weight percent table",
        min_bytes=50_000,
    ),
    DatasetAsset(
        key="langlais_mag",
        scope="mars",
        url="https://zenodo.org/api/records/3876714/files/Langlais2019.sh.gz/content",
        rel_path="mars/Langlais2019.sh.gz",
        description="Langlais et al. (2019) Mars degree-134 crustal magnetic SH model (Zenodo 3876714)",
        min_bytes=50_000,
    ),
)
