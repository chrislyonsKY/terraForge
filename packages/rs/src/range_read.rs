//! Concurrent HTTP range reads via Tokio + reqwest.
//!
//! Issues multiple HTTP range requests in parallel against a single URL
//! (typically a COG or cloud-hosted raster) and returns the byte buffers.
//! This is substantially faster than Python's httpx async client for
//! high-concurrency scenarios (50+ simultaneous range requests) because
//! Tokio's runtime avoids Python's GIL contention on I/O completion.

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use tokio::runtime::Runtime;

/// Issue concurrent HTTP range reads against a single URL.
///
/// Each range is a (start, end) byte offset tuple. All requests run
/// concurrently on the Tokio runtime. Results are returned in the same
/// order as the input ranges.
///
/// Arguments:
///     url: The HTTP(S) URL to read from.
///     ranges: List of (start, end) byte offset tuples.
///
/// Returns:
///     List of bytes objects, one per range.
///
/// Raises:
///     RuntimeError: If any request fails.
#[pyfunction]
pub fn parallel_range_read<'py>(
    py: Python<'py>,
    url: String,
    ranges: Vec<(u64, u64)>,
) -> PyResult<Vec<Bound<'py, PyBytes>>> {
    let rt = Runtime::new().map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("Failed to create Tokio runtime: {e}"))
    })?;

    let results = rt.block_on(async {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(60))
            .build()
            .map_err(|e| {
                pyo3::exceptions::PyRuntimeError::new_err(format!(
                    "Failed to create HTTP client: {e}"
                ))
            })?;

        let mut handles = Vec::with_capacity(ranges.len());

        for (start, end) in &ranges {
            let client = client.clone();
            let url = url.clone();
            let start = *start;
            let end = *end;

            handles.push(tokio::spawn(async move {
                let resp = client
                    .get(&url)
                    .header("Range", format!("bytes={start}-{end}"))
                    .send()
                    .await
                    .map_err(|e| format!("Request failed for range {start}-{end}: {e}"))?;

                if !resp.status().is_success() && resp.status().as_u16() != 206 {
                    return Err(format!(
                        "HTTP {} for range {start}-{end}",
                        resp.status()
                    ));
                }

                resp.bytes()
                    .await
                    .map_err(|e| format!("Failed to read body for range {start}-{end}: {e}"))
            }));
        }

        let mut results = Vec::with_capacity(handles.len());
        for handle in handles {
            let data = handle
                .await
                .map_err(|e| {
                    pyo3::exceptions::PyRuntimeError::new_err(format!("Task join error: {e}"))
                })?
                .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e))?;
            results.push(data);
        }

        Ok::<Vec<_>, PyErr>(results)
    })?;

    results
        .into_iter()
        .map(|data| Ok(PyBytes::new(py, &data)))
        .collect()
}
