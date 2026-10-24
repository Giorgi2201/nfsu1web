//! Minimal virtual-LAN switch for NFSU1 browser clients (`/lan`).
//!
//! Speaks the control/binary protocol expected by nfsu2-web `web/src/net`
//! (hello/welcome/peers/delta/ping, binary frames with VIP rewrite). Hosts a
//! minimal Online lobby stand-in at 10.77.0.1 (see `online.rs`). No free-roam hub.

use std::collections::HashMap;
use std::net::Ipv4Addr;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use axum::extract::ws::{Message, WebSocket};
use axum::extract::{FromRef, Query, State, WebSocketUpgrade};
use axum::http::{HeaderMap, StatusCode};
use axum::response::IntoResponse;
use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::sync::{mpsc, watch, Mutex, Semaphore};
use tokio::time::timeout;

use crate::handlers::AppState;
use crate::online::{self, OnlineHost, ONLINE_VIP};

const NET: u32 = u32::from_be_bytes([10, 77, 0, 0]);
const MASK_STR: &str = "255.255.248.0";
const BROADCAST: u32 = 0xffff_ffff;
const KIND_LAN_UDP: u8 = 3;
const KIND_LAN_TCP: u8 = 4;
const KIND_LAN_ICMP: u8 = 5;
const KIND_BUNDLE: u8 = 32;
const MAX_NAME: usize = 32;
/// F_DATA (16) + NET_MAX_PAYLOAD (1472) from web/src/net/proto.ts
const MAX_FRAME: usize = 1488;
const MAX_MESSAGE: usize = 64 * 1024;
const MAX_QUEUE: usize = 256;
const MAX_BUNDLE_FRAMES: usize = 256;
const IO_TIMEOUT: Duration = Duration::from_secs(10);

/// A full queue disconnects the recipient rather than silently losing TCP data.
#[derive(Clone)]
struct Outbox {
    tx: mpsc::Sender<Message>,
    stop: watch::Sender<bool>,
}

impl Outbox {
    fn send(&self, message: Message) {
        if self.tx.try_send(message).is_err() {
            self.stop.send_replace(true);
        }
    }
}

/// Per-connection burst budget; accounts for expanded bundles and fan-out.
struct Budget {
    remaining: f64,
    updated: Instant,
    rate: f64,
}

impl Budget {
    fn new(rate: f64) -> Self {
        Self {
            remaining: rate * 2.0,
            updated: Instant::now(),
            rate,
        }
    }

    fn take(&mut self, amount: usize) -> bool {
        let now = Instant::now();
        self.remaining = (self.remaining
            + now.duration_since(self.updated).as_secs_f64() * self.rate)
            .min(self.rate * 2.0);
        self.updated = now;
        if amount as f64 > self.remaining {
            return false;
        }
        self.remaining -= amount as f64;
        true
    }
}

#[derive(Clone)]
pub struct LanSwitch {
    inner: Arc<Mutex<SwitchInner>>,
    online: Arc<Mutex<OnlineHost>>,
    next_id: Arc<AtomicU64>,
    connections: Arc<Semaphore>,
    max_players: usize,
}

struct SwitchInner {
    peers: HashMap<u64, Peer>,
    by_vip: HashMap<u32, u64>,
    /// Host bits of the /21; .1 is reserved for the Online host.
    next_host: u32,
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
    tx: Outbox,
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
    pub fn new(max_players: usize) -> Self {
        let switch = Self {
            inner: Arc::new(Mutex::new(SwitchInner::new())),
            online: Arc::new(Mutex::new(OnlineHost::new())),
            next_id: Arc::new(AtomicU64::new(0)),
            connections: Arc::new(Semaphore::new(max_players + 32)),
            max_players,
        };
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
    let Ok(permit) = switch.connections.clone().try_acquire_owned() else {
        return (StatusCode::SERVICE_UNAVAILABLE, "connection limit").into_response();
    };
    ws.max_message_size(MAX_MESSAGE)
        .max_frame_size(MAX_MESSAGE)
        .on_upgrade(move |socket| async move {
            let _permit = permit;
            peer_task(socket, switch).await;
        })
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
    let Some(host) = headers
        .get(axum::http::header::HOST)
        .and_then(|h| h.to_str().ok())
    else {
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
        "full": players >= switch.max_players,
    }))
}

async fn peer_task(socket: WebSocket, switch: LanSwitch) {
    let (mut sink, mut stream) = socket.split();
    let (sender, mut rx) = mpsc::channel::<Message>(MAX_QUEUE);
    let (stop, mut stopped) = watch::channel(false);
    let tx = Outbox {
        tx: sender,
        stop: stop.clone(),
    };
    let bundles = Arc::new(AtomicBool::new(false));
    let writer_bundles = bundles.clone();
    let mut pump = tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            // Drain what is already ready without adding a race-packet timer.
            let mut ready = vec![msg];
            while ready.len() < 32 {
                match rx.try_recv() {
                    Ok(msg) => ready.push(msg),
                    Err(_) => break,
                }
            }
            let messages = pack_messages(ready, writer_bundles.load(Ordering::Relaxed));
            let sent = timeout(IO_TIMEOUT, async {
                for msg in messages {
                    sink.feed(msg).await?;
                }
                sink.flush().await
            })
            .await;
            if !matches!(sent, Ok(Ok(()))) {
                break;
            }
        }
        stop.send_replace(true);
    });

    let mut peer_id: Option<u64> = None;
    let mut hello_done = false;
    let mut message_budget = Budget::new(2048.0);
    let mut byte_budget = Budget::new(1024.0 * 1024.0);
    let hello_deadline = tokio::time::Instant::now() + IO_TIMEOUT;

    loop {
        let deadline = if hello_done {
            tokio::time::Instant::now() + Duration::from_secs(90)
        } else {
            hello_deadline
        };
        let received = tokio::select! {
            _ = stopped.changed() => break,
            msg = tokio::time::timeout_at(deadline, stream.next()) => msg,
        };
        let Ok(Some(Ok(msg))) = received else { break };
        let length = match &msg {
            Message::Text(v) => v.len(),
            Message::Binary(v) | Message::Ping(v) | Message::Pong(v) => v.len(),
            Message::Close(_) => 0,
        };
        if !message_budget.take(1) || !byte_budget.take(length) {
            break;
        }
        match msg {
            Message::Text(text) => {
                if text.len() > 4096 {
                    break;
                }
                let Ok(v) = serde_json::from_str::<Value>(&text) else {
                    break;
                };
                let t = v.get("t").and_then(|x| x.as_str()).unwrap_or("");
                if !hello_done {
                    if t != "hello" {
                        break;
                    }
                    bundles.store(
                        v.get("bundle").and_then(Value::as_u64) == Some(1),
                        Ordering::Relaxed,
                    );
                    match attach(&switch, &v, tx.clone()).await {
                        Ok(id) => {
                            peer_id = Some(id);
                            hello_done = true;
                        }
                        Err(reason) => {
                            tx.send(Message::Close(Some(axum::extract::ws::CloseFrame {
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
                        tx.send(Message::Text(
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
                    let Ok(frames) = unpack_frames(&bin) else {
                        break;
                    };
                    let mut allowed = true;
                    for frame in frames {
                        if !message_budget.take(1)
                            || !route_frame(&switch, id, frame, &mut byte_budget).await
                        {
                            allowed = false;
                            break;
                        }
                    }
                    if !allowed {
                        break;
                    }
                } else {
                    break;
                }
            }
            Message::Close(_) => break,
            Message::Ping(p) => {
                tx.send(Message::Pong(p));
            }
            Message::Pong(_) => {}
        }
    }

    if let Some(id) = peer_id {
        detach(&switch, id).await;
    }
    drop(tx);
    // Flush a queued close when possible, but never retain a blocked writer.
    if timeout(IO_TIMEOUT, &mut pump).await.is_err() {
        pump.abort();
        let _ = pump.await;
    }
}

async fn attach(switch: &LanSwitch, hello: &Value, tx: Outbox) -> Result<u64, &'static str> {
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
        if g.peers.len() >= switch.max_players {
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
    tx.send(Message::Text(
        json!({
            "t": "welcome",
            "vip": vip,
            "vipStr": vip_str,
            "mask": MASK_STR,
            "token": token,
            "bundle": 1,
        })
        .to_string()
        .into(),
    ));
    tx.send(Message::Text(
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
        peer.vip
    };
    let replies = switch.online.lock().await.disconnect_peer(gone);
    deliver_online_replies(switch, &replies).await;
    switch.inner.lock().await.by_vip.remove(&gone);
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
    let targets: Vec<Outbox> = {
        let g = switch.inner.lock().await;
        g.peers
            .values()
            .filter(|p| except != Some(p.id))
            .map(|p| p.tx.clone())
            .collect()
    };
    for tx in targets {
        tx.send(msg.clone());
    }
}

async fn route_frame(
    switch: &LanSwitch,
    from_id: u64,
    mut frame: Vec<u8>,
    budget: &mut Budget,
) -> bool {
    if frame.len() < 16 || frame.len() > MAX_FRAME {
        return false;
    }
    let kind = frame[0];
    if !matches!(kind, KIND_LAN_UDP | KIND_LAN_TCP | KIND_LAN_ICMP) {
        return false;
    }

    let (src_vip, lan_open, dst, targets) = {
        let g = switch.inner.lock().await;
        let Some(from) = g.peers.get(&from_id) else {
            return false;
        };
        let src = from.vip;
        let lan = from.lan;
        let mut dst = u32::from_be_bytes(frame[8..12].try_into().unwrap());
        if dst == (NET | 2047) {
            dst = BROADCAST;
        }
        let mut outs: Vec<(u64, Outbox, bool)> = Vec::new();
        if dst == BROADCAST {
            for p in g.peers.values() {
                if p.id == from_id || !lan || !p.lan {
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
    if !budget.take(frame.len() * targets.len().max(1)) {
        return false;
    }

    if dst == ONLINE_VIP {
        let replies = {
            let mut online = switch.online.lock().await;
            online.on_frame(&frame)
        };
        if !budget.take(replies.iter().map(Vec::len).sum()) {
            return false;
        }
        deliver_online_replies(switch, &replies).await;
        return true;
    }

    let lan_kind = matches!(kind, KIND_LAN_UDP | KIND_LAN_TCP | KIND_LAN_ICMP);
    let msg = Message::Binary(frame.into());

    for (_id, tx, peer_lan) in targets {
        if dst == BROADCAST && lan_kind && (!lan_open || !peer_lan) {
            continue;
        }
        tx.send(msg.clone());
    }
    true
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
            tx.send(Message::Binary(r.clone().into()));
        }
    }
}

fn alloc_vip(g: &mut SwitchInner) -> Option<u32> {
    for _ in 0..2045 {
        let host = g.next_host;
        g.next_host = if host >= 2046 { 2 } else { host + 1 };
        let vip = NET | host;
        if !g.by_vip.contains_key(&vip) {
            return Some(vip);
        }
    }
    None
}

/// Upstream kind-32 wire format: header, then destination count, reserved,
/// frame length (big endian), optional destinations, and the original frame.
fn unpack_frames(bytes: &[u8]) -> Result<Vec<Vec<u8>>, ()> {
    if bytes.first() != Some(&KIND_BUNDLE) {
        return if (16..=MAX_FRAME).contains(&bytes.len()) {
            Ok(vec![bytes.to_vec()])
        } else {
            Err(())
        };
    }
    if bytes.len() < 4 || bytes.len() > MAX_MESSAGE {
        return Err(());
    }
    let mut frames = Vec::new();
    let mut at = 4;
    while at < bytes.len() {
        let header = bytes.get(at..at + 4).ok_or(())?;
        let destinations = usize::from(header[0]);
        let size = usize::from(u16::from_be_bytes([header[2], header[3]]));
        if destinations > 64 || !(16..=MAX_FRAME).contains(&size) {
            return Err(());
        }
        let start = at + 4 + destinations * 4;
        let frame = bytes.get(start..start + size).ok_or(())?;
        if !matches!(frame[0], KIND_LAN_UDP | KIND_LAN_TCP | KIND_LAN_ICMP) {
            return Err(());
        }
        if frames.len() + destinations.max(1) > MAX_BUNDLE_FRAMES {
            return Err(());
        }
        if destinations == 0 {
            frames.push(frame.to_vec());
        } else {
            for destination in bytes[at + 4..start].chunks_exact(4) {
                let mut copy = frame.to_vec();
                copy[8..12].copy_from_slice(destination);
                frames.push(copy);
            }
        }
        at = start + size;
    }
    if frames.is_empty() {
        Err(())
    } else {
        Ok(frames)
    }
}

fn flush_bundle(bundle: &mut Vec<u8>, count: &mut usize, out: &mut Vec<Message>) {
    if *count == 0 {
        return;
    }
    let bytes = std::mem::replace(bundle, vec![KIND_BUNDLE, 0, 0, 0]);
    // Keep single-frame writes compatible and avoid unnecessary framing.
    out.push(Message::Binary(if *count == 1 {
        bytes[8..].to_vec().into()
    } else {
        bytes.into()
    }));
    *count = 0;
}

/// Bundle only queued binary frames; never reorder control messages or wait
/// for a timer (upstream likewise sends LAN race traffic immediately).
fn pack_messages(messages: Vec<Message>, enabled: bool) -> Vec<Message> {
    if !enabled {
        return messages;
    }
    let mut out = Vec::new();
    let mut bundle = vec![KIND_BUNDLE, 0, 0, 0];
    let mut count = 0;
    for message in messages {
        match message {
            Message::Binary(bytes) if (16..=MAX_FRAME).contains(&bytes.len()) => {
                if bundle.len() + 4 + bytes.len() > MAX_MESSAGE {
                    flush_bundle(&mut bundle, &mut count, &mut out);
                }
                bundle.extend_from_slice(&[0, 0]);
                bundle.extend_from_slice(&(bytes.len() as u16).to_be_bytes());
                bundle.extend_from_slice(&bytes);
                count += 1;
            }
            other => {
                flush_bundle(&mut bundle, &mut count, &mut out);
                out.push(other);
            }
        }
    }
    flush_bundle(&mut bundle, &mut count, &mut out);
    out
}

fn clean_name(raw: &str) -> String {
    let mut out = String::new();
    for ch in raw.chars() {
        if out.len() + ch.len_utf8() > MAX_NAME {
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bundles_preserve_frames_and_control_order() {
        let mut a = vec![0; 24];
        a[0] = KIND_LAN_TCP;
        let mut b = a.clone();
        b[23] = 7;
        let packed = pack_messages(
            vec![
                Message::Binary(a.clone().into()),
                Message::Binary(b.clone().into()),
                Message::Text("control".into()),
                Message::Binary(a.clone().into()),
            ],
            true,
        );
        assert_eq!(packed.len(), 3);
        let Message::Binary(bundle) = &packed[0] else {
            panic!("not binary")
        };
        assert_eq!(unpack_frames(bundle).unwrap(), vec![a.clone(), b]);
        assert!(matches!(&packed[1], Message::Text(t) if t.as_str() == "control"));
        let Message::Binary(single) = &packed[2] else {
            panic!("not binary")
        };
        assert_eq!(single.as_ref(), a);
        assert!(unpack_frames(&bundle[..bundle.len() - 1]).is_err());
        let mut nested = bundle.to_vec();
        nested[8] = KIND_BUNDLE;
        assert!(unpack_frames(&nested).is_err());
    }

    #[test]
    fn addresses_cross_subnet_octet_without_duplicates() {
        let mut g = SwitchInner::new();
        let mut addresses = std::collections::HashSet::new();
        for _ in 0..2045 {
            let vip = alloc_vip(&mut g).unwrap();
            assert!(addresses.insert(vip));
        }
        assert!(addresses.contains(&u32::from_be_bytes([10, 77, 1, 0])));
        assert!(!addresses.contains(&ONLINE_VIP));
        assert!(!addresses.contains(&(NET | 2047)));
    }

    #[tokio::test]
    async fn full_queue_disconnects_instead_of_dropping_tcp() {
        let (tx, _rx) = mpsc::channel(1);
        let (stop, stopped) = watch::channel(false);
        let outbox = Outbox { tx, stop };
        outbox.send(Message::Text("first".into()));
        assert!(!*stopped.borrow());
        outbox.send(Message::Text("second".into()));
        assert!(*stopped.borrow());
    }
}
