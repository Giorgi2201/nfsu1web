use std::path::{Component, Path, PathBuf};

use axum::http::StatusCode;

#[derive(Debug)]
pub struct RequestError {
    pub status: StatusCode,
    pub message: &'static str,
}

impl RequestError {
    pub fn new(status: StatusCode, message: &'static str) -> Self {
        Self { status, message }
    }
}

/// Resolve URL path segments under `root`. Rejects traversal and any symlink.
pub fn resolve_under(root: &Path, parts: &[String]) -> Result<PathBuf, RequestError> {
    let root = root
        .canonicalize()
        .map_err(|_| RequestError::new(StatusCode::NOT_FOUND, "not found"))?;
    let mut current = root.clone();
    for (i, part) in parts.iter().enumerate() {
        if part.is_empty()
            || part == "."
            || part == ".."
            || part.contains('/')
            || part.contains('\\')
            || part.contains('\0')
        {
            return Err(RequestError::new(StatusCode::BAD_REQUEST, "invalid path"));
        }
        let candidate = current.join(part);
        if candidate.is_symlink() {
            return Err(RequestError::new(StatusCode::NOT_FOUND, "not found"));
        }
        current = candidate;
        match current.canonicalize() {
            Ok(resolved) => {
                if !resolved.starts_with(&root) {
                    return Err(RequestError::new(StatusCode::NOT_FOUND, "not found"));
                }
                current = resolved;
            }
            Err(_) if i + 1 != parts.len() => {
                return Err(RequestError::new(StatusCode::NOT_FOUND, "not found"));
            }
            Err(_) => return Ok(current),
        }
    }
    Ok(current)
}

pub fn decoded_parts(raw_path: &str) -> Result<Vec<String>, RequestError> {
    if !raw_path.starts_with('/') {
        return Err(RequestError::new(StatusCode::BAD_REQUEST, "invalid path"));
    }
    let mut raw_parts: Vec<&str> = raw_path.split('/').skip(1).collect();
    if raw_parts.last() == Some(&"") {
        raw_parts.pop();
    }
    let mut result = Vec::with_capacity(raw_parts.len());
    for raw in raw_parts {
        if raw.contains('%') {
            let bytes = raw.as_bytes();
            let mut i = 0;
            while i < bytes.len() {
                if bytes[i] == b'%' {
                    if i + 2 >= bytes.len()
                        || !bytes[i + 1].is_ascii_hexdigit()
                        || !bytes[i + 2].is_ascii_hexdigit()
                    {
                        return Err(RequestError::new(
                            StatusCode::BAD_REQUEST,
                            "malformed percent escape",
                        ));
                    }
                    i += 3;
                } else {
                    i += 1;
                }
            }
        }
        let part = percent_encoding::percent_decode_str(raw)
            .decode_utf8()
            .map_err(|_| RequestError::new(StatusCode::BAD_REQUEST, "invalid path"))?;
        if part == "."
            || part == ".."
            || part.contains('/')
            || part.contains('\\')
            || part.contains('\0')
        {
            return Err(RequestError::new(StatusCode::BAD_REQUEST, "invalid path"));
        }
        result.push(part.into_owned());
    }
    Ok(result)
}

pub fn relative_posix(path: &Path, root: &Path) -> Option<String> {
    path.strip_prefix(root).ok().map(|p| {
        p.components()
            .filter_map(|c| match c {
                Component::Normal(s) => Some(s.to_string_lossy()),
                _ => None,
            })
            .collect::<Vec<_>>()
            .join("/")
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_dotdot_segment() {
        assert!(decoded_parts("/a/../b").is_err());
    }

    #[test]
    fn decodes_simple() {
        assert_eq!(
            decoded_parts("/Cars/car.bin").unwrap(),
            vec!["Cars", "car.bin"]
        );
    }
}
