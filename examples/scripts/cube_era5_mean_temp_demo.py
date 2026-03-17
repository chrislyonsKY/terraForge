"""ERA5 mean temperature from Planetary Computer Zarr store.

Computes and visualizes the temporal mean of 2m temperature from ERA5
reanalysis data accessed via the Planetary Computer STAC API.

Output: examples/outputs/cube_stats_era5_mean_temp.png

Data source: ERA5 on Microsoft Planetary Computer (public with SAS token)

Usage::

    python examples/scripts/cube_era5_mean_temp_demo.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, "packages/core/src")
sys.path.insert(0, "packages/cube/src")

from earthforge.core.palettes import VIRIDIS

OUTPUT_DIR = Path("examples/outputs")
OUTPUT_PNG = OUTPUT_DIR / "cube_stats_era5_mean_temp.png"
OUTPUT_TXT = OUTPUT_DIR / "cube_stats_era5_mean_temp.txt"

# ERA5 Zarr store on Planetary Computer (public access)
ERA5_ZARR_URL = "https://era5pds.s3.amazonaws.com/zarr/2025/01/data/air_temperature_at_2_metres.zarr"

KY_LAT_RANGE = (37.0, 38.5)
KY_LON_RANGE = (-85.5, -84.0)


def main() -> None:
    """Compute and visualize ERA5 mean temperature."""
    print("EarthForge — ERA5 Mean Temperature from Real Data")
    print("=" * 52)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import xarray as xr
    except ImportError as e:
        print(f"Required: pip install matplotlib xarray ({e})")
        return

    # Open real ERA5 Zarr store
    print(f"Opening ERA5 Zarr: {ERA5_ZARR_URL}")
    try:
        ds = xr.open_zarr(ERA5_ZARR_URL, consolidated=True)
    except Exception:
        # Fall back to the Planetary Computer catalog
        print("Direct Zarr access failed. Trying Planetary Computer STAC...")
        try:
            import pystac_client
            catalog = pystac_client.Client.open(
                "https://planetarycomputer.microsoft.com/api/stac/v1"
            )
            era5 = catalog.get_collection("era5-pds")
            # Get the Zarr asset URL
            asset = era5.assets.get("zarr-abfs") or era5.assets.get("zarr-https")
            if asset:
                print(f"Found ERA5 Zarr asset: {asset.href}")
                ds = xr.open_zarr(asset.href)
            else:
                print("Cannot locate ERA5 Zarr asset. Using subset approach...")
                ds = None
        except Exception as exc:
            print(f"Planetary Computer access failed: {exc}")
            print("\nThis script requires network access to ERA5 data.")
            print("The ERA5 dataset may require authentication or a SAS token.")
            print("See: https://planetarycomputer.microsoft.com/dataset/era5-pds")
            return

    if ds is None:
        return

    # Find temperature variable
    temp_var = None
    for name in ["air_temperature_at_2_metres", "t2m", "temperature", "2t"]:
        if name in ds.data_vars:
            temp_var = name
            break

    if temp_var is None:
        print(f"No temperature variable found. Available: {list(ds.data_vars)}")
        ds.close()
        return

    print(f"Temperature variable: {temp_var}")
    print(f"Dimensions: {dict(ds[temp_var].dims)}")

    # Select Kentucky region
    lat_dim = "latitude" if "latitude" in ds.dims else "lat"
    lon_dim = "longitude" if "longitude" in ds.dims else "lon"

    subset = ds[temp_var].sel(
        {lat_dim: slice(*KY_LAT_RANGE), lon_dim: slice(*KY_LON_RANGE)}
    )

    # Compute temporal mean
    print("Computing temporal mean...")
    time_dim = "time" if "time" in subset.dims else "time1"
    mean_temp = subset.mean(dim=time_dim).load().values

    print(f"  Shape: {mean_temp.shape}")
    print(f"  Range: {np.nanmin(mean_temp):.1f} K — {np.nanmax(mean_temp):.1f} K")
    mean_c = np.nanmean(mean_temp) - 273.15
    print(f"  Mean: {np.nanmean(mean_temp):.1f} K ({mean_c:.1f} C)")

    # Get coordinate arrays for extent
    lats = subset[lat_dim].values
    lons = subset[lon_dim].values

    # Render
    print("Rendering map...")
    fig, (ax_map, ax_stats) = plt.subplots(
        1, 2, figsize=(13, 7),
        gridspec_kw={"width_ratios": [3, 1]},
    )

    im = ax_map.imshow(
        mean_temp,
        extent=[lons.min(), lons.max(), lats.min(), lats.max()],
        origin="lower" if lats[0] < lats[-1] else "upper",
        cmap="viridis",
        aspect="auto",
    )
    ax_map.set_title(
        f"ERA5 Mean 2m Temperature\n"
        f"Central Kentucky | Temporal Mean",
        fontsize=13, fontweight="bold",
    )
    ax_map.set_xlabel("Longitude", fontsize=10)
    ax_map.set_ylabel("Latitude", fontsize=10)

    cbar = fig.colorbar(im, ax=ax_map, shrink=0.8, pad=0.02)
    cbar.set_label("Temperature (K)", fontsize=11)

    # Stats sidebar
    ax_stats.axis("off")
    min_k = float(np.nanmin(mean_temp))
    max_k = float(np.nanmax(mean_temp))
    mean_k = float(np.nanmean(mean_temp))
    std_k = float(np.nanstd(mean_temp))

    stats_text = (
        f"Statistics\n"
        f"{'─' * 22}\n"
        f"Variable:  {temp_var}\n"
        f"Operation: mean\n"
        f"Source:    ERA5\n"
        f"{'─' * 22}\n"
        f"Min:    {min_k:>7.1f} K\n"
        f"        ({min_k - 273.15:>7.1f} °C)\n"
        f"Max:    {max_k:>7.1f} K\n"
        f"        ({max_k - 273.15:>7.1f} °C)\n"
        f"Mean:   {mean_k:>7.1f} K\n"
        f"        ({mean_k - 273.15:>7.1f} °C)\n"
        f"Std:    {std_k:>7.2f} K\n"
        f"{'─' * 22}\n"
        f"Grid:   {mean_temp.shape[0]}x{mean_temp.shape[1]}\n"
        f"CRS:    EPSG:4326\n"
    )
    ax_stats.text(
        0.05, 0.95, stats_text,
        transform=ax_stats.transAxes,
        fontsize=10, fontfamily="monospace",
        verticalalignment="top",
    )

    fig.text(
        0.5, 0.01,
        f"Data: ECMWF ERA5 via Planetary Computer | "
        f"Palette: viridis (colorblind-safe) | "
        f"EarthForge v1.0.0 | {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        ha="center", fontsize=7, color="gray",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(OUTPUT_PNG), dpi=150, bbox_inches="tight")
    plt.close(fig)
    ds.close()
    print(f"Saved: {OUTPUT_PNG}")

    sidecar = (
        f"Alt Text: Mean 2m temperature map over Central Kentucky from ERA5 "
        f"reanalysis data. Temperature ranges from {min_k:.1f} K "
        f"({min_k - 273.15:.1f} °C) to {max_k:.1f} K ({max_k - 273.15:.1f} °C), "
        f"rendered with the viridis colorblind-safe palette.\n\n"
        f"Data Source: ECMWF, ERA5 Reanalysis\n"
        f"URL: {ERA5_ZARR_URL}\n"
        f"Access Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        f"License: Copernicus Climate Data Store License\n"
        f"Spatial Extent: lat={KY_LAT_RANGE}, lon={KY_LON_RANGE}\n\n"
        f"Generated By: earthforge v1.0.0\n"
        f"Script: examples/scripts/cube_era5_mean_temp_demo.py\n"
        f"Parameters: variable={temp_var}, operation=mean, region=Central KY\n"
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
    )
    OUTPUT_TXT.write_text(sidecar, encoding="utf-8")
    print(f"Saved: {OUTPUT_TXT}")


if __name__ == "__main__":
    main()
