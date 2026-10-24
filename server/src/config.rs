use std::collections::HashMap;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::SystemTime;

use axum::http::StatusCode;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::manifest::{build_manifest, Manifest};
use crate::paths::{decoded_parts, resolve_under, RequestError};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FileStamp {
    pub size: u64,
    pub modified: SystemTime,
}

impl FileStamp {
    pub fn from_meta(meta: &fs::Metadata) -> Self {
        Self {
            size: meta.len(),
            modified: meta.modified().unwrap_or(SystemTime::UNIX_EPOCH),
        }
    }
}

#[derive(Clone)]
pub struct OverlayFile {
    pub path: PathBuf,
    pub stamp: FileStamp,
    pub mtime: i64,
}

pub struct Config {
    pub dist: PathBuf,
    pub wasm: PathBuf,
    pub data: PathBuf,
    pub module_hash: String,
    pub module_stamp: FileStamp,
    pub game_json: Vec<u8>,
    pub font_files: HashMap<String, OverlayFile>,
    pub online_files: HashMap<String, OverlayFile>,
    manifest: Mutex<Option<Manifest>>,
}

impl Config {
    pub fn load(
        dist: PathBuf,
        wasm: PathBuf,
        metadata: PathBuf,
        data: PathBuf,
        hd_fonts: Option<PathBuf>,
        online_data: Option<PathBuf>,
        strict_data: bool,
    ) -> Result<Self, String> {
        let errors = validate(&dist, &wasm, &metadata, &data, strict_data);
        if !errors.is_empty() {
            return Err(errors.join("\n"));
        }
        let module_hash = hash_file(&wasm).map_err(|e| e.to_string())?;
        let module_stamp = FileStamp::from_meta(&fs::metadata(&wasm).map_err(|e| e.to_string())?);
        let mut game_info: Map<String, Value> =
            serde_json::from_str(&fs::read_to_string(&metadata).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?;
        let mut font_files = HashMap::new();
        if let Some(dir) = hd_fonts {
            if game_info.get("hdFonts").and_then(|v| v.as_i64()) != Some(1) {
                return Err(
                    "rebuild Wasm with HD font scaling support before enabling fonts".into(),
                );
            }
            font_files = load_fonts(&dir, &data)?;
        }
        let online_files = match online_data {
            Some(dir) => load_overlay(
                &dir,
                &data,
                "nfsu1-online-data",
                &["global/globalb.lzc"],
                false,
            )?,
            None => HashMap::new(),
        };
        let short = &module_hash[..12.min(module_hash.len())];
        game_info.insert("rev".into(), Value::String(format!("nfsu1-local-{short}")));
        game_info.insert("module".into(), Value::String(module_hash.clone()));
        let game_json = serde_json::to_vec(&Value::Object(game_info)).map_err(|e| e.to_string())?;
        Ok(Self {
            dist: dist.canonicalize().map_err(|e| e.to_string())?,
            wasm: wasm.canonicalize().map_err(|e| e.to_string())?,
            data: data.canonicalize().map_err(|e| e.to_string())?,
            module_hash,
            module_stamp,
            game_json,
            font_files,
            online_files,
            manifest: Mutex::new(None),
        })
    }

    pub fn get_manifest(&self) -> Result<Manifest, RequestError> {
        let mut guard = self
            .manifest
            .lock()
            .map_err(|_| RequestError::new(StatusCode::INTERNAL_SERVER_ERROR, "lock poisoned"))?;
        if guard.is_none() {
            let mut manifest = build_manifest(&self.data).map_err(|_| {
                RequestError::new(StatusCode::INTERNAL_SERVER_ERROR, "manifest failed")
            })?;
            for entry in &mut manifest.files {
                let key = entry.p.to_ascii_lowercase();
                if let Some(file) = self
                    .font_files
                    .get(&key)
                    .or_else(|| self.online_files.get(&key))
                {
                    entry.s = Some(file.stamp.size);
                    entry.m = Some(file.mtime);
                }
            }
            *guard = Some(manifest);
        }
        Ok(guard.as_ref().unwrap().clone())
    }

    pub fn wasm_stamp_matches(&self) -> bool {
        fs::metadata(&self.wasm)
            .ok()
            .map(|m| FileStamp::from_meta(&m) == self.module_stamp)
            .unwrap_or(false)
    }
}

fn load_fonts(directory: &Path, data: &Path) -> Result<HashMap<String, OverlayFile>, String> {
    load_overlay(
        directory,
        data,
        "nfsu1-hd-fonts",
        &["global/globala.bun", "languages/languagetextures.bin"],
        true,
    )
}

fn load_overlay(
    directory: &Path,
    data: &Path,
    kind: &str,
    allowed: &[&str],
    require_all: bool,
) -> Result<HashMap<String, OverlayFile>, String> {
    let report: Value = serde_json::from_str(
        &fs::read_to_string(directory.join("manifest.json")).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    if report.get("kind").and_then(|v| v.as_str()) != Some(kind) {
        return Err(format!("expected a prepared {kind} manifest"));
    }
    let entries = report
        .get("files")
        .and_then(|v| v.as_array())
        .ok_or_else(|| format!("{kind} manifest missing files"))?;
    let paths: Vec<String> = entries
        .iter()
        .filter_map(|e| {
            e.get("path")
                .and_then(|p| p.as_str())
                .map(|s| s.to_ascii_lowercase())
        })
        .collect();
    if paths.len() != entries.len()
        || (require_all && entries.len() != allowed.len())
        || paths.iter().any(|p| !allowed.contains(&p.as_str()))
        || paths
            .iter()
            .enumerate()
            .any(|(i, p)| paths[..i].contains(p))
    {
        return Err(format!("{kind} manifest has invalid replacement paths"));
    }
    let mut out = HashMap::new();
    for entry in entries {
        let path_str = entry
            .get("path")
            .and_then(|p| p.as_str())
            .ok_or_else(|| "overlay entry missing path".to_string())?;
        let parts = decoded_parts(&format!("/{path_str}")).map_err(|e| e.message.to_string())?;
        let original = resolve_under(data, &parts).map_err(|e| e.message.to_string())?;
        let replacement =
            resolve_under(&directory.join("data"), &parts).map_err(|e| e.message.to_string())?;
        let source_sha = entry
            .get("source_sha256")
            .and_then(|v| v.as_str())
            .ok_or_else(|| "overlay entry missing source_sha256".to_string())?;
        let sha = entry
            .get("sha256")
            .and_then(|v| v.as_str())
            .ok_or_else(|| "overlay entry missing sha256".to_string())?;
        if hash_file(&original).map_err(|e| e.to_string())? != source_sha {
            return Err(format!(
                "{kind} source does not match: {path_str}; rebuild the overlay"
            ));
        }
        let digest = hash_file(&replacement).map_err(|e| e.to_string())?;
        if digest != sha {
            return Err(format!("{kind} output hash mismatch: {path_str}"));
        }
        let stamp = FileStamp::from_meta(&fs::metadata(&replacement).map_err(|e| e.to_string())?);
        let mtime = 0x0001_0000_0000_i64 + i64::from_str_radix(&digest[..8], 16).unwrap_or(0);
        out.insert(
            path_str.to_ascii_lowercase(),
            OverlayFile {
                path: replacement,
                stamp,
                mtime,
            },
        );
    }
    Ok(out)
}

pub fn validate(
    dist: &Path,
    wasm: &Path,
    metadata: &Path,
    data: &Path,
    strict_data: bool,
) -> Vec<String> {
    let mut errors = Vec::new();
    for (label, path) in [
        ("dist", dist),
        ("wasm", wasm),
        ("metadata", metadata),
        ("data", data),
    ] {
        if !path.exists() {
            errors.push(format!("{label} path does not exist: {}", path.display()));
        }
    }
    if dist.exists()
        && (!dist.is_dir() || !dist.join("index.html").is_file() || !dist.join("main.js").is_file())
    {
        errors.push(format!(
            "dist must contain index.html and main.js: {}",
            dist.display()
        ));
    }
    if wasm.exists() && !wasm.is_file() {
        errors.push(format!("wasm is not a file: {}", wasm.display()));
    }
    if metadata.exists() {
        match fs::read_to_string(metadata)
            .ok()
            .and_then(|s| serde_json::from_str::<Value>(&s).ok())
        {
            Some(Value::Object(info)) => {
                for key in ["pages", "maxPages", "guestEnd", "size"] {
                    let ok = info.get(key).and_then(|v| v.as_u64()).is_some();
                    if !ok {
                        errors.push(format!("invalid metadata {key}"));
                    }
                }
                if let (Some(size), Ok(meta)) = (
                    info.get("size").and_then(|v| v.as_u64()),
                    fs::metadata(wasm),
                ) {
                    if wasm.is_file() && size != meta.len() {
                        errors.push(format!("size is {size}, but wasm is {} bytes", meta.len()));
                    }
                }
            }
            _ => errors.push(format!("invalid metadata {}", metadata.display())),
        }
    }
    if data.exists() && !data.is_dir() {
        errors.push(format!("data is not a directory: {}", data.display()));
    }
    if strict_data && data.exists() && data.is_dir() {
        if let Ok(walker) = walkdir_symlinks(data) {
            for path in walker {
                errors.push(format!(
                    "unexpected symlink in private data: {}",
                    path.display()
                ));
            }
        }
    }
    errors
}

fn walkdir_symlinks(root: &Path) -> std::io::Result<Vec<PathBuf>> {
    let mut out = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        for entry in fs::read_dir(&dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_symlink() {
                out.push(path);
            } else if path.is_dir() {
                stack.push(path);
            }
        }
    }
    Ok(out)
}

pub fn hash_file(path: &Path) -> std::io::Result<String> {
    let mut file = fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 1 << 20];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(hex::encode(hasher.finalize()))
}
