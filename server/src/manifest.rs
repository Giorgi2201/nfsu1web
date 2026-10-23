use std::fs;
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::Serialize;

use crate::paths::relative_posix;

#[derive(Clone, Debug, Serialize)]
pub struct ManifestEntry {
    pub p: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub d: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub s: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub m: Option<i64>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Manifest {
    pub files: Vec<ManifestEntry>,
}

pub fn build_manifest(data: &Path) -> std::io::Result<Manifest> {
    let root = data.canonicalize()?;
    let mut files = Vec::new();
    walk(&root, &root, &mut files)?;
    Ok(Manifest { files })
}

fn walk(root: &Path, current: &Path, files: &mut Vec<ManifestEntry>) -> std::io::Result<()> {
    let mut dirs = Vec::new();
    let mut names = Vec::new();
    for entry in fs::read_dir(current)? {
        let entry = entry?;
        let path = entry.path();
        let name = entry.file_name();
        if path.is_symlink() {
            continue;
        }
        if path.is_dir() {
            dirs.push(name);
        } else {
            names.push(name);
        }
    }
    dirs.sort_by_key(|a| a.to_ascii_lowercase());
    names.sort_by_key(|a| a.to_ascii_lowercase());

    if current != root {
        if let Some(rel) = relative_posix(current, root) {
            files.push(ManifestEntry {
                p: rel,
                d: Some(true),
                s: None,
                m: None,
            });
        }
    }

    for name in names {
        let path = current.join(&name);
        if path.is_symlink() {
            continue;
        }
        let meta = match fs::metadata(&path) {
            Ok(m) if m.is_file() => m,
            _ => continue,
        };
        let Some(rel) = relative_posix(&path, root) else {
            continue;
        };
        files.push(ManifestEntry {
            p: rel,
            d: None,
            s: Some(meta.len()),
            m: Some(mtime_secs(&meta)),
        });
    }

    for name in dirs {
        let path = current.join(name);
        if path.is_symlink() {
            continue;
        }
        walk(root, &path, files)?;
    }
    Ok(())
}

fn mtime_secs(meta: &fs::Metadata) -> i64 {
    meta.modified()
        .unwrap_or(SystemTime::UNIX_EPOCH)
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}
