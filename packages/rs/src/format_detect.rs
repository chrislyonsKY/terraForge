//! Rayon-parallel format detection via magic byte sniffing.
//!
//! Reads the first 16 bytes of each file in parallel using Rayon's thread pool,
//! then matches against known magic byte signatures to determine the file format.
//!
//! This is significantly faster than Python's sequential file-open-read-close
//! loop when processing thousands of files (e.g., scanning a directory of
//! geospatial datasets).

use pyo3::prelude::*;
use rayon::prelude::*;
use std::fs::File;
use std::io::Read;
use std::path::Path;

/// Known magic byte signatures for geospatial formats.
///
/// Each entry is (magic_bytes, offset, format_name).
const SIGNATURES: &[(&[u8], usize, &str)] = &[
    // TIFF (GeoTIFF, COG) — little-endian and big-endian
    (b"II\x2a\x00", 0, "geotiff"),
    (b"MM\x00\x2a", 0, "geotiff"),
    // BigTIFF
    (b"II\x2b\x00", 0, "geotiff"),
    (b"MM\x00\x2b", 0, "geotiff"),
    // Apache Parquet
    (b"PAR1", 0, "parquet"),
    // HDF5 / NetCDF-4
    (b"\x89HDF\r\n\x1a\n", 0, "hdf5"),
    // NetCDF classic (CDF)
    (b"CDF\x01", 0, "netcdf"),
    (b"CDF\x02", 0, "netcdf"),
    // FlatGeobuf
    (b"fgb\x03", 0, "flatgeobuf"),
    // GeoJSON / JSON (starts with '{' or '[')
    (b"{", 0, "json"),
    (b"[", 0, "json"),
    // Shapefile (.shp magic)
    (b"\x00\x00\x27\x0a", 0, "shapefile"),
    // COPC / LAZ (LASF magic)
    (b"LASF", 0, "las"),
    // PNG
    (b"\x89PNG", 0, "png"),
    // JPEG
    (b"\xff\xd8\xff", 0, "jpeg"),
];

/// Detect the format of a single file by reading its magic bytes.
fn detect_single(path: &str) -> String {
    let p = Path::new(path);

    // For directories, check for Zarr markers
    if p.is_dir() {
        if p.join(".zarray").exists()
            || p.join(".zmetadata").exists()
            || p.join(".zattrs").exists()
        {
            return "zarr".to_string();
        }
        return "directory".to_string();
    }

    // Try extension first for formats without distinct magic bytes
    if let Some(ext) = p.extension().and_then(|e| e.to_str()) {
        match ext.to_lowercase().as_str() {
            "zarr" => return "zarr".to_string(),
            "gpkg" => return "geopackage".to_string(),
            "geojson" => return "geojson".to_string(),
            "geoparquet" => return "geoparquet".to_string(),
            "copc.laz" | "copc" => return "copc".to_string(),
            _ => {}
        }
    }

    // Read first 16 bytes for magic byte matching
    let mut buf = [0u8; 16];
    let bytes_read = match File::open(p).and_then(|mut f| f.read(&mut buf)) {
        Ok(n) => n,
        Err(_) => return "unknown".to_string(),
    };

    if bytes_read == 0 {
        return "unknown".to_string();
    }

    let data = &buf[..bytes_read];

    for &(magic, offset, format) in SIGNATURES {
        if offset + magic.len() <= data.len() && &data[offset..offset + magic.len()] == magic {
            return format.to_string();
        }
    }

    "unknown".to_string()
}

/// Detect file formats for a batch of paths in parallel.
///
/// Uses Rayon's parallel iterator to sniff magic bytes concurrently across
/// all available CPU cores. Returns a list of format strings in the same
/// order as the input paths.
///
/// Arguments:
///     paths: List of file paths to detect.
///
/// Returns:
///     List of format name strings (e.g., "geotiff", "parquet", "zarr", "unknown").
#[pyfunction]
pub fn detect_format_batch(paths: Vec<String>) -> Vec<String> {
    paths.par_iter().map(|p| detect_single(p)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[test]
    fn test_tiff_detection() {
        let mut f = NamedTempFile::new().unwrap();
        f.write_all(b"II\x2a\x00rest_of_header").unwrap();
        let result = detect_single(f.path().to_str().unwrap());
        assert_eq!(result, "geotiff");
    }

    #[test]
    fn test_parquet_detection() {
        let mut f = NamedTempFile::new().unwrap();
        f.write_all(b"PAR1rest_of_file").unwrap();
        let result = detect_single(f.path().to_str().unwrap());
        assert_eq!(result, "parquet");
    }

    #[test]
    fn test_unknown_format() {
        let mut f = NamedTempFile::new().unwrap();
        f.write_all(b"UNKNOWN_MAGIC").unwrap();
        let result = detect_single(f.path().to_str().unwrap());
        assert_eq!(result, "unknown");
    }

    #[test]
    fn test_batch_detection() {
        let mut tiff = NamedTempFile::new().unwrap();
        tiff.write_all(b"II\x2a\x00data").unwrap();

        let mut pq = NamedTempFile::new().unwrap();
        pq.write_all(b"PAR1data").unwrap();

        let paths = vec![
            tiff.path().to_str().unwrap().to_string(),
            pq.path().to_str().unwrap().to_string(),
        ];
        let results = detect_format_batch(paths);
        assert_eq!(results, vec!["geotiff", "parquet"]);
    }
}
