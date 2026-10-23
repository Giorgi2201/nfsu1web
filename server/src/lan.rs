//! Minimal virtual-LAN switch for NFSU1 browser clients (`/lan`).
//!
//! Speaks the control/binary protocol expected by nfsu2-web `web/src/net`
//! (hello/welcome/peers/delta/ping, binary frames with VIP rewrite). Hosts a
//! minimal Online lobby stand-in at 10.77.0.1 (see `online.rs`). No free-roam hub.

use std::collections::HashMap;
use std::net::Ipv4Addr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use axum::extract::ws::{Message, WebSocket};
use axum::extract::{FromRef, Query, State, WebSocketUpgrade};
use axum::http::{HeaderMap, StatusCode};
use axum::response::IntoResponse;
use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::sync::{mpsc, Mutex};

use crate::handlers::AppState;
use crate::online::{self, OnlineHost, ONLINE_VIP};

const NET: u32 = u32::from_be_bytes([10, 77, 0, 0]);
const MASK_STR: &str = "255.255.255.0";
const BROADCAST: u32 = 0xffff_ffff;
const KIND_LAN_UDP: u8 = 3;
const KIND_LAN_TCP: u8 = 4;
const KIND_LAN_ICMP: u8 = 5;
const KIND_BUNDLE: u8 = 32;
const MAX_PEERS: usize = 32;
const MAX_NAME: usize = 32;
/// F_DATA (16) + NET_MAX_PAYLOAD (1472) from web/src/net/proto.ts
const MAX_FRAME: usize = 1488;

#[derive(Clone)]
pub struct LanSwitch {
    inner: Arc<Mutex<SwitchInner>>,
    online: Arc<Mutex<OnlineHost>>,
    next_id: Arc<AtomicU64>,
}

impl Default for LanSwitch {
    fn default() -> Self {
        Self {
            inner: Arc::new(Mutex::new(SwitchInner::new())),
            online: Arc::new(Mutex::new(OnlineHost::new())),
            next_id: Arc::new(AtomicU64::new(0)),
        }
    }
}

struct SwitchInner {
    peers: HashMap<u64, Peer>,
    by_vip: HashMap<u32, u64>,
    /// Next host octet to try (2..=254). `.1` reserved for a future lobby host.
    next_host: u8,
}

impl SwitchInner {
    fn new() -> Self {
        Self {
            peers: HashMap::new(),
            by_vip: HashMap::new(),
            next_host: 2,
        }
    }
}

struct Peer {
    id: u64,
    vip: u32,
    name: String,
    lan: bool,
    tx: mpsc::UnboundedSender<Message>,
}

#[derive(Debug, Deserialize)]
pub struct LanQuery {
    /// Present when the page reconnects (`/lan?resume`); address reclaim is not
    /// implemented yet — clients get a fresh VIP.
    #[serde(default)]
    #[allow(dead_code)]
    resume: Option<String>,
}

impl LanSwitch {
    pub fn new() -> Self {
        let switch = Self::default();
        switch.spawn_online_keepalive();
        switch
    }

    /// nfsuserver sends `~png` after ~30s idle so clients do not drop the lobby.
    fn spawn_online_keepalive(&self) {
        let switch = self.clone();
        tokio::spawn(async move {
            let mut tick = tokio::time::interval(std::time::Duration::from_secs(10));
            tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
            loop {
                tick.tick().await;
                let replies = {
                    let mut online = switch.online.lock().await;
                    online.keepalive_pings()
                };
                deliver_online_replies(&switch, &replies).await;
            }
        });
    }

    pub async fn player_counts(&self) -> (usize, usize) {
        let g = self.inner.lock().await;
        let n = g.peers.len();
        let online = g.peers.values().filter(|p| p.lan).count();
        (n, online)
    }
}

impl FromRef<AppState> for LanSwitch {
    fn from_ref(state: &AppState) -> Self {
        state.lan.clone()
    }
}

pub async fn lan_ws(
    ws: WebSocketUpgrade,
    Query(_q): Query<LanQuery>,
    State(switch): State<LanSwitch>,
    headers: HeaderMap,
) -> impl IntoResponse {
    if let Err(resp) = check_lan_origin(&headers) {
        return resp.into_response();
    }
    ws.on_upgrade(move |socket| peer_task(socket, switch))
        .into_response()
}

/// Reject cross-origin `/lan` when an Origin is present. Missing Origin is
/// allowed for local tooling (Node smoke); browsers always send Origin.
fn check_lan_origin(headers: &HeaderMap) -> Result<(), (StatusCode, &'static str)> {
    let Some(origin) = headers.get(axum::http::header::ORIGIN) else {
        return Ok(());
    };
    let Ok(origin) = origin.to_str() else {
        return Err((StatusCode::FORBIDDEN, "bad Origin"));
    };
    if origin == "null" {
        return Err((StatusCode::FORBIDDEN, "null Origin"));
    }
    let Some(host) = headers.get(axum::http::header::HOST).and_then(|h| h.to_str().ok()) else {
        return Err((StatusCode::FORBIDDEN, "missing Host"));
    };
    let Ok(origin_url) = origin.parse::<axum::http::Uri>() else {
        return Err((StatusCode::FORBIDDEN, "bad Origin"));
    };
    let Some(origin_host) = origin_url.host() else {
        return Err((StatusCode::FORBIDDEN, "bad Origin"));
    };
    let origin_authority = match origin_url.port_u16() {
        Some(p) => format!("{origin_host}:{p}"),
        None => origin_host.to_string(),
    };
    if !origin_authority.eq_ignore_ascii_case(host) {
        return Err((StatusCode::FORBIDDEN, "Origin does not match Host"));
    }
    Ok(())
}

pub async fn players(State(switch): State<LanSwitch>) -> impl IntoResponse {
    let (players, online) = switch.player_counts().await;
    axum::Json(json!({
        "players": players,
        "online": online,
        "full": players >= MAX_PEERS,
    }))
}

async fn peer_task(socket: WebSocket, switch: LanSwitch) {
    let (mut sink, mut stream) = socket.split();
    let (tx, mut rx) = mpsc::unbounded_channel::<Message>();
    let pump = tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            if sink.send(msg).await.is_err() {
                break;
            }
        }
    });

    let mut peer_id: Option<u64> = None;
    let mut hello_done = false;

    while let Some(Ok(msg)) = stream.next().await {
        match msg {
            Message::Text(text) => {
                let Ok(v) = serde_json::from_str::<Value>(&text) else {
                    continue;
                };
                let t = v.get("t").and_then(|x| x.as_str()).unwrap_or("");
                if !hello_done {
                    if t != "hello" {
                        continue;
                    }
                    match attach(&switch, &v, tx.clone()).await {
                        Ok(id) => {
                            peer_id = Some(id);
                            hello_done = true;
                        }
                        Err(reason) => {
                            let _ = tx.send(Message::Close(Some(axum::extract::ws::CloseFrame {
                                code: 1013,
                                reason: reason.into(),
                            })));
                            break;
                        }
                    }
                    continue;
                }
                let Some(id) = peer_id else { continue };
                match t {
                    "ping" => {
                        let idn = v.get("id").and_then(|x| x.as_i64()).unwrap_or(0);
                        let _ = tx.send(Message::Text(
                            json!({ "t": "pong", "id": idn }).to_string().into(),
                        ));
                    }
                    "lan" => {
                        let on = v.get("on").and_then(|x| x.as_u64()).unwrap_or(0) != 0;
                        set_lan(&switch, id, on).await;
                    }
                    _ => {}
                }
            }
            Message::Binary(bin) => {
                if let Some(id) = peer_id {
                    route_frame(&switch, id, bin.to_vec()).await;
                }
            }
            Message::Close(_) => break,
            Message::Ping(p) => {
                let _ = tx.send(Message::Pong(p));
            }
            Message::Pong(_) => {}
        }
    }

    if let Some(id) = peer_id {
        detach(&switch, id).await;
    }
    drop(tx);
    let _ = pump.await;
}

async fn attach(
    switch: &LanSwitch,
    hello: &Value,
    tx: mpsc::UnboundedSender<Message>,
) -> Result<u64, &'static str> {
    let name = clean_name(
        hello
            .get("name")
            .and_then(|x| x.as_str())
            .unwrap_or("Player"),
    );
    let lan = hello.get("lan").and_then(|x| x.as_u64()).unwrap_or(0) != 0;
    let id = switch.next_id.fetch_add(1, Ordering::Relaxed) + 1;

    let (vip, peers_snapshot) = {
        let mut g = switch.inner.lock().await;
        if g.peers.len() >= MAX_PEERS {
            return Err("LAN full");
        }
        let Some(vip) = alloc_vip(&mut g) else {
            return Err("LAN full");
        };
        g.peers.insert(
            id,
            Peer {
                id,
                vip,
                name: name.clone(),
                lan,
                tx: tx.clone(),
            },
        );
        g.by_vip.insert(vip, id);
        let mut peers: Vec<Value> = g
            .peers
            .values()
            .map(|p| json!({ "vip": p.vip, "name": p.name }))
            .collect();
        peers.push(online::server_peer_json());
        (vip, peers)
    };

    let token = format!("{:032x}", rand::random::<u128>());
    let vip_str = Ipv4Addr::from(vip).to_string();
    let _ = tx.send(Message::Text(
        json!({
            "t": "welcome",
            "vip": vip,
            "vipStr": vip_str,
            "mask": MASK_STR,
            "token": token,
            "bundle": 0,
        })
        .to_string()
        .into(),
    ));
    let _ = tx.send(Message::Text(
        json!({ "t": "peers", "peers": peers_snapshot })
            .to_string()
            .into(),
    ));

    broadcast_delta(
        switch,
        vec![json!({ "vip": vip, "name": name })],
        Vec::new(),
        Some(id),
    )
    .await;
    Ok(id)
}

async fn detach(switch: &LanSwitch, id: u64) {
    let gone = {
        let mut g = switch.inner.lock().await;
        let Some(peer) = g.peers.remove(&id) else {
            return;
        };
        g.by_vip.remove(&peer.vip);
        peer.vip
    };
    broadcast_delta(switch, Vec::new(), vec![gone], None).await;
}

async fn set_lan(switch: &LanSwitch, id: u64, on: bool) {
    let mut g = switch.inner.lock().await;
    if let Some(p) = g.peers.get_mut(&id) {
        p.lan = on;
    }
}

async fn broadcast_delta(
    switch: &LanSwitch,
    peers: Vec<Value>,
    gone: Vec<u32>,
    except: Option<u64>,
) {
    let msg = Message::Text(
        json!({ "t": "delta", "peers": peers, "gone": gone })
            .to_string()
            .into(),
    );
    let targets: Vec<mpsc::UnboundedSender<Message>> = {
        let g = switch.inner.lock().await;
        g.peers
            .values()
            .filter(|p| except != Some(p.id))
            .map(|p| p.tx.clone())
            .collect()
    };
    for tx in targets {
        let _ = tx.send(msg.clone());
    }
}

async fn route_frame(switch: &LanSwitch, from_id: u64, mut frame: Vec<u8>) {
    if frame.len() < 16 || frame.len() > MAX_FRAME {
        return;
    }
    let kind = frame[0];
    if kind == KIND_BUNDLE {
        // Welcome advertises bundle:0; ignore unexpected bundles.
        return;
    }

    let (src_vip, lan_open, dst, targets) = {
        let g = switch.inner.lock().await;
        let Some(from) = g.peers.get(&from_id) else {
            return;
        };
        let src = from.vip;
        let lan = from.lan;
        let dst = u32::from_be_bytes(frame[8..12].try_into().unwrap());
        let mut outs: Vec<(u64, mpsc::UnboundedSender<Message>, bool)> = Vec::new();
        if dst == BROADCAST {
            for p in g.peers.values() {
                if p.id == from_id {
                    continue;
                }
                outs.push((p.id, p.tx.clone(), p.lan));
            }
        } else if dst != ONLINE_VIP {
            if let Some(&tid) = g.by_vip.get(&dst) {
                if tid != from_id {
                    if let Some(p) = g.peers.get(&tid) {
                        outs.push((p.id, p.tx.clone(), p.lan));
                    }
                }
            }
        }
        (src, lan, dst, outs)
    };

    frame[4..8].copy_from_slice(&src_vip.to_be_bytes());

    if dst == ONLINE_VIP {
        let replies = {
            let mut online = switch.online.lock().await;
            online.on_frame(&frame)
        };
        deliver_online_replies(switch, &replies).await;
        return;
    }

    let lan_kind = matches!(kind, KIND_LAN_UDP | KIND_LAN_TCP | KIND_LAN_ICMP);
    let msg = Message::Binary(frame.into());

    for (_id, tx, peer_lan) in targets {
        if dst == BROADCAST && lan_kind && (!lan_open || !peer_lan) {
            continue;
        }
        let _ = tx.send(msg.clone());
    }
}

/// Online host replies set dst VIP at bytes 8..12; send each to that peer
/// (not only the peer that triggered the request). Needed for room +usr/+agm.
async fn deliver_online_replies(switch: &LanSwitch, replies: &[Vec<u8>]) {
    if replies.is_empty() {
        return;
    }
    let g = switch.inner.lock().await;
    for r in replies {
        if r.len() < 16 {
            continue;
        }
        let reply_dst = u32::from_be_bytes(r[8..12].try_into().unwrap());
        let tx = g
            .by_vip
            .get(&reply_dst)
            .and_then(|tid| g.peers.get(tid))
            .map(|p| p.tx.clone());
        if let Some(tx) = tx {
            let _ = tx.send(Message::Binary(r.clone().into()));
        }
    }
}

fn alloc_vip(g: &mut SwitchInner) -> Option<u32> {
    for _ in 0..253 {
        let host = g.next_host;
        g.next_host = if host >= 254 { 2 } else { host + 1 };
        let vip = NET | u32::from(host);
        if !g.by_vip.contains_key(&vip) {
            return Some(vip);
        }
    }
    None
}

fn clean_name(raw: &str) -> String {
    let mut out = String::new();
    for ch in raw.chars() {
        if out.len() >= MAX_NAME {
            break;
        }
        if ch.is_control() || ch == '\u{7f}' {
            continue;
        }
        out.push(ch);
    }
    if out.is_empty() {
        "Player".into()
    } else {
        out
    }
}
