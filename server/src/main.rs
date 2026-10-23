mod config;
mod handlers;
mod manifest;
mod paths;

use std::env;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::process::ExitCode;
use std::sync::Arc;

use axum::routing::get;
use axum::Router;
use clap::Parser;
use handlers::{handle, AppState};

#[derive(Parser, Debug)]
#[command(
    name = "nfsu1-server",
    about = "Serve the NFSU1 browser build and game data"
)]
struct Args {
    /// Built web dist directory
    #[arg(long, default_value = "work/upstream/nfsu2-web/web/dist")]
    dist: PathBuf,

    /// Private NFSU1 wasm module
    #[arg(long, default_value = "work/upstream/nfsu2-web/out/web/nfsu1.wasm")]
    wasm: PathBuf,

    /// NFSU1 module metadata JSON
    #[arg(long, default_value = "work/upstream/nfsu2-web/out/web/nfsu1.json")]
    metadata: PathBuf,

    /// Private game data directory (must include a real Speed.exe, no symlinks)
    #[arg(long, default_value = "work/data")]
    data: PathBuf,

    /// Prepared HD fonts directory from prepare_hd_fonts.py
    #[arg(long)]
    hd_fonts: Option<PathBuf>,

    /// Bind address. Loopback by default.
    #[arg(long, default_value = "127.0.0.1")]
    host: String,

    /// HTTP port (defaults to the PORT environment variable)
    #[arg(long)]
    port: Option<u16>,

    /// Allow non-loopback bind
    #[arg(long)]
    public: bool,

    /// Validate inputs without binding a port
    #[arg(long)]
    check: bool,
}

#[tokio::main]
async fn main() -> ExitCode {
    let mut args = Args::parse();
    if let Ok(port) = env::var("PORT") {
        if args.port.is_none() {
            match port.parse::<u16>() {
                Ok(p) => args.port = Some(p),
                Err(_) => {
                    eprintln!("error: PORT must be an integer");
                    return ExitCode::from(1);
                }
            }
        }
    }
    if env::var("NFSU1_PUBLIC").ok().as_deref() == Some("1") {
        args.public = true;
    }
    if let Ok(host) = env::var("NFSU1_HOST") {
        args.host = host;
    }
    let port = args.port.unwrap_or(8765);

    let loopback = matches!(args.host.as_str(), "127.0.0.1" | "::1" | "localhost");
    if !loopback && !args.public {
        eprintln!("error: only loopback hosts are allowed without --public (or NFSU1_PUBLIC=1)");
        return ExitCode::from(1);
    }

    // Relative paths resolve from the process cwd (start.sh cds to the repo root).
    let cwd = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let dist = resolve_path(&cwd, &args.dist);
    let wasm = resolve_path(&cwd, &args.wasm);
    let metadata = resolve_path(&cwd, &args.metadata);
    let data = resolve_path(&cwd, &args.data);
    let hd_fonts = args.hd_fonts.map(|p| resolve_path(&cwd, &p));

    let config = match config::Config::load(
        dist,
        wasm,
        metadata,
        data,
        hd_fonts,
        /* strict_data */ args.check || !args.public,
    ) {
        Ok(c) => c,
        Err(err) => {
            for line in err.lines() {
                eprintln!("error: {line}");
            }
            return ExitCode::from(1);
        }
    };

    if args.check {
        println!("Local server inputs are ready.");
        return ExitCode::SUCCESS;
    }

    let fonts = !config.font_files.is_empty();
    let state = AppState {
        config: Arc::new(config),
    };
    let app = Router::new()
        .fallback(get(handle).head(handle))
        .with_state(state);

    let addr: SocketAddr = match format!("{}:{}", args.host, port).parse() {
        Ok(a) => a,
        Err(e) => {
            eprintln!("error: invalid bind address: {e}");
            return ExitCode::from(1);
        }
    };

    let listener = match tokio::net::TcpListener::bind(addr).await {
        Ok(l) => l,
        Err(e) if e.kind() == std::io::ErrorKind::AddrInUse => {
            eprintln!(
                "error: {addr} is already in use. If the game server is already running, open \
                 http://{}/. Stop that server before restarting with different options; \
                 keep the same address to retain your profile.",
                display_url(&args.host, port)
            );
            return ExitCode::from(1);
        }
        Err(e) => {
            eprintln!("error: cannot start server on {addr}: {e}");
            return ExitCode::from(1);
        }
    };

    let bound = listener.local_addr().unwrap_or(addr);
    println!(
        "Serving NFSU1 build at http://{}/ (Ctrl-C to stop)",
        display_url(&bound.ip().to_string(), bound.port())
    );
    if fonts {
        println!("HD fonts enabled (local overlay; gauges unchanged).");
    } else {
        println!("Font assets: stock (no --hd-fonts overlay selected).");
    }

    if let Err(e) = axum::serve(listener, app).await {
        eprintln!("error: server failed: {e}");
        return ExitCode::from(1);
    }
    ExitCode::SUCCESS
}

fn resolve_path(repo: &std::path::Path, path: &std::path::Path) -> PathBuf {
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        repo.join(path)
    }
}

fn display_url(host: &str, port: u16) -> String {
    let host = if host == "0.0.0.0" || host == "::" {
        "127.0.0.1"
    } else {
        host
    };
    format!("{host}:{port}")
}
