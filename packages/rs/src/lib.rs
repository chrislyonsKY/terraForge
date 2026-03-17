//! EarthForge Rust acceleration extensions.
//!
//! Provides three performance-critical functions exposed to Python via PyO3:
//!
//! 1. `detect_format_batch` — Rayon-parallel magic byte sniffing across many files
//! 2. `parallel_range_read` — Tokio-based concurrent HTTP range reads
//! 3. `read_geoparquet_fast` — GeoArrow-based GeoParquet reading with Arrow FFI
//!
//! Every function here has a pure-Python fallback in the core package.
//! `pip install earthforge` works without Rust; these are optional accelerators.

mod format_detect;
mod geoparquet;
mod range_read;

use pyo3::prelude::*;

/// EarthForge Rust acceleration module.
///
/// Functions:
///   - detect_format_batch(paths) -> list[str]
///   - parallel_range_read(url, ranges) -> list[bytes]
///   - read_geoparquet_fast(path) -> pyarrow.Table
#[pymodule]
fn earthforge_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(format_detect::detect_format_batch, m)?)?;
    m.add_function(wrap_pyfunction!(range_read::parallel_range_read, m)?)?;
    m.add_function(wrap_pyfunction!(geoparquet::read_geoparquet_fast, m)?)?;
    Ok(())
}
