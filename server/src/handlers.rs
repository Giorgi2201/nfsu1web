use std::io::SeekFrom;
use std::path::Path;
use std::sync::Arc;

use axum::body::Body;
use axum::extract::State;
use axum::http::{header, HeaderMap, HeaderValue, Method, StatusCode, Uri};
use axum::response::{IntoResponse, Response};
use serde::Deserialize;
use tokio::io::{AsyncReadExt, AsyncSeekExt};
use tokio_util::io::ReaderStream;

use crate::config::{Config, FileStamp};
use crate::paths::{decoded_parts, resolve_under, RequestError};

#[derive(Clone)]
pub struct AppState {
    pub config: Arc<Config>,
}

pub async fn handle(
    State(state): State<AppState>,
    method: Method,
    uri: Uri,
    headers: HeaderMap,
) -> Response {
    let head = method == Method::HEAD;
    match dispatch(&state, head, &uri, &headers).await {
        Ok(resp) => resp,
        Err(err) => error_response(err.status, err.message, head),
    }
}

async fn dispatch(
    state: &AppState,
    head: bool,
    uri: &Uri,
    headers: &HeaderMap,
) -> Result<Response, RequestError> {
    let path = uri.path();
    let send_body = !head;
    let cfg = &state.config;

    if path == "/game.json" {
        return Ok(bytes_response(
            StatusCode::OK,
            "application/json",
            cfg.game_json.clone(),
            send_body,
            "no-store",
        ));
    }

    if path == "/game.wasm" {
        let query: WasmQuery = uri
            .query()
            .and_then(serde_urlencoded_simple)
            .unwrap_or_default();
        if !query.v.is_empty() && query.v != cfg.module_hash {
            return Err(RequestError::new(
                StatusCode::CONFLICT,
                "module changed; reload game.json",
            ));
        }
        if !query.v.is_empty() {
            if !cfg.wasm_stamp_matches() {
                return Err(RequestError::new(
                    StatusCode::CONFLICT,
                    "module changed; restart the local server",
                ));
            }
            return send_file(
                &cfg.wasm,
                "application/wasm",
                send_body,
                true,
                "private, max-age=31536000, immutable",
                Some(&cfg.module_stamp),
                headers,
            )
            .await;
        }
        return send_file(
            &cfg.wasm,
            "application/wasm",
            send_body,
            true,
            "no-store",
            None,
            headers,
        )
        .await;
    }

    if path == "/data-manifest" {
        let body = serde_json::to_vec(&cfg.get_manifest()?)
            .map_err(|_| RequestError::new(StatusCode::INTERNAL_SERVER_ERROR, "manifest encode"))?;
        return Ok(bytes_response(
            StatusCode::OK,
            "application/json",
            body,
            send_body,
            "no-store",
        ));
    }

    if path == "/data" || path.starts_with("/data/") {
        let suffix = path.strip_prefix("/data/").unwrap_or("");
        let parts = if suffix.is_empty() {
            Vec::new()
        } else {
            decoded_parts(&format!("/{suffix}"))?
        };
        let key = parts.join("/").to_ascii_lowercase();
        if let Some(font) = cfg.font_files.get(&key) {
            let mime = mime_for(&font.path);
            return send_file(
                &font.path,
                mime,
                send_body,
                true,
                "no-store",
                Some(&font.stamp),
                headers,
            )
            .await;
        }
        let target = resolve_under(&cfg.data, &parts)?;
        let mime = mime_for(&target);
        return send_file(&target, mime, send_body, true, "no-store", None, headers).await;
    }

    if path == "/healthz" {
        return Ok(bytes_response(
            StatusCode::OK,
            "text/plain; charset=utf-8",
            b"ok\n".to_vec(),
            send_body,
            "no-store",
        ));
    }

    let parts = decoded_parts(path)?;
    let mut target = resolve_under(&cfg.dist, &parts)?;
    if target.is_dir() {
        let mut index_parts = parts;
        index_parts.push("index.html".into());
        target = resolve_under(&cfg.dist, &index_parts)?;
    }
    let mime = mime_for(&target);
    send_file(&target, mime, send_body, false, "no-store", None, headers).await
}

#[derive(Default, Deserialize)]
struct WasmQuery {
    #[serde(default)]
    v: String,
}

fn serde_urlencoded_simple(q: &str) -> Option<WasmQuery> {
    let mut v = String::new();
    for pair in q.split('&') {
        let mut it = pair.splitn(2, '=');
        let key = it.next()?;
        let val = it.next().unwrap_or("");
        if key == "v" {
            v = percent_encoding::percent_decode_str(val)
                .decode_utf8()
                .ok()?
                .into_owned();
        }
    }
    Some(WasmQuery { v })
}

fn mime_for(path: &Path) -> &'static str {
    mime_guess::from_path(path)
        .first_raw()
        .unwrap_or("application/octet-stream")
}

async fn send_file(
    path: &Path,
    content_type: &str,
    send_body: bool,
    ranges: bool,
    cache_control: &str,
    expected_stamp: Option<&FileStamp>,
    headers: &HeaderMap,
) -> Result<Response, RequestError> {
    let meta = path
        .metadata()
        .map_err(|_| RequestError::new(StatusCode::NOT_FOUND, "not found"))?;
    if !meta.is_file() {
        return Err(RequestError::new(StatusCode::NOT_FOUND, "not found"));
    }
    let stamp = FileStamp::from_meta(&meta);
    if let Some(expected) = expected_stamp {
        if &stamp != expected {
            return Err(RequestError::new(
                StatusCode::CONFLICT,
                "module changed; restart the local server",
            ));
        }
    }
    let size = meta.len();
    let mut start = 0u64;
    let mut end = size.saturating_sub(1);
    let mut status = StatusCode::OK;

    if ranges {
        if let Some(range) = headers.get(header::RANGE).and_then(|v| v.to_str().ok()) {
            if let Some((s, e)) = parse_range(range, size) {
                start = s;
                end = e;
                status = StatusCode::PARTIAL_CONTENT;
            } else {
                let mut resp = Response::builder()
                    .status(StatusCode::RANGE_NOT_SATISFIABLE)
                    .header(header::CONTENT_RANGE, format!("bytes */{size}"))
                    .header(header::CONTENT_LENGTH, "0")
                    .body(Body::empty())
                    .unwrap();
                isolation_headers(resp.headers_mut());
                return Ok(resp);
            }
        }
    }

    let length = if size == 0 { 0 } else { end - start + 1 };
    let body = if send_body && length > 0 {
        let mut file = tokio::fs::File::open(path)
            .await
            .map_err(|_| RequestError::new(StatusCode::NOT_FOUND, "not found"))?;
        file.seek(SeekFrom::Start(start))
            .await
            .map_err(|_| RequestError::new(StatusCode::NOT_FOUND, "not found"))?;
        let limited = file.take(length);
        let stream = ReaderStream::with_capacity(limited, 64 * 1024);
        Body::from_stream(stream)
    } else {
        Body::empty()
    };

    let mut builder = Response::builder()
        .status(status)
        .header(header::CONTENT_TYPE, content_type)
        .header(header::ACCEPT_RANGES, if ranges { "bytes" } else { "none" })
        .header(header::CONTENT_LENGTH, length.to_string())
        .header(header::CACHE_CONTROL, cache_control)
        .header(header::LAST_MODIFIED, httpdate(&stamp.modified));
    if status == StatusCode::PARTIAL_CONTENT {
        builder = builder.header(header::CONTENT_RANGE, format!("bytes {start}-{end}/{size}"));
    }
    let mut resp = builder.body(body).unwrap();
    isolation_headers(resp.headers_mut());
    Ok(resp)
}

fn parse_range(header: &str, size: u64) -> Option<(u64, u64)> {
    let header = header.trim();
    let rest = header.strip_prefix("bytes=")?;
    if size == 0 {
        return None;
    }
    let (a, b) = rest.split_once('-')?;
    if !a.is_empty() {
        let start: u64 = a.parse().ok()?;
        let end = if b.is_empty() {
            size - 1
        } else {
            b.parse::<u64>().ok()?.min(size - 1)
        };
        if start >= size || end < start {
            return None;
        }
        Some((start, end))
    } else if !b.is_empty() {
        let length: u64 = b.parse().ok()?;
        let start = size.saturating_sub(length);
        Some((start, size - 1))
    } else {
        None
    }
}

fn bytes_response(
    status: StatusCode,
    content_type: &str,
    body: Vec<u8>,
    send_body: bool,
    cache_control: &str,
) -> Response {
    let len = body.len();
    let mut resp = Response::builder()
        .status(status)
        .header(header::CONTENT_TYPE, content_type)
        .header(header::CONTENT_LENGTH, len.to_string())
        .header(header::CACHE_CONTROL, cache_control)
        .body(if send_body {
            Body::from(body)
        } else {
            Body::empty()
        })
        .unwrap();
    isolation_headers(resp.headers_mut());
    resp
}

fn error_response(status: StatusCode, message: &str, head: bool) -> Response {
    let body = format!("{message}\n");
    let mut resp = Response::builder()
        .status(status)
        .header(header::CONTENT_TYPE, "text/plain; charset=utf-8")
        .header(header::CONTENT_LENGTH, body.len().to_string())
        .header(header::CACHE_CONTROL, "no-store")
        .body(if head {
            Body::empty()
        } else {
            Body::from(body)
        })
        .unwrap();
    isolation_headers(resp.headers_mut());
    resp
}

fn isolation_headers(headers: &mut HeaderMap) {
    headers.insert(
        "cross-origin-opener-policy",
        HeaderValue::from_static("same-origin"),
    );
    headers.insert(
        "cross-origin-embedder-policy",
        HeaderValue::from_static("require-corp"),
    );
    headers.insert(
        "x-content-type-options",
        HeaderValue::from_static("nosniff"),
    );
}

fn httpdate(time: &std::time::SystemTime) -> String {
    let dur = time
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    chrono::DateTime::<chrono::Utc>::from_timestamp(dur.as_secs() as i64, 0)
        .unwrap_or(chrono::DateTime::UNIX_EPOCH)
        .format("%a, %d %b %Y %H:%M:%S GMT")
        .to_string()
}

impl IntoResponse for RequestError {
    fn into_response(self) -> Response {
        error_response(self.status, self.message, false)
    }
}
