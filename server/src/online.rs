//! NFSU1 Online lobby stand-in on virtual VIP 10.77.0.1.
//!
//! Full nfsuserver Dirtysock command surface (see `docs/online-protocol.md`).
//! Accounts / persona lists / stats / news / rankings are in-memory hardcoded
//! stand-ins (no DB).

use std::collections::{HashMap, HashSet};
use std::time::{Duration, Instant};

pub const ONLINE_VIP: u32 = u32::from_be_bytes([10, 77, 0, 1]);

const KIND_LAN_TCP: u8 = 4;
const KIND_LAN_ICMP: u8 = 5;
const TCP_SYN: u8 = 1;
const TCP_SYNACK: u8 = 2;
const TCP_RST: u8 = 3;
const TCP_DATA: u8 = 4;
const TCP_FIN: u8 = 5;

const PORT_REDIR: u16 = 10900;
const PORT_LOBBY: u16 = 10901;
const PORT_REPORT: u16 = 10980;
const PORT_CLIENT_REP: u16 = 10800;

const F_DATA: usize = 16;
const LAN_HDR: usize = 8;
const MAX_PEER_CONNECTIONS: usize = 16;
const MAX_COMMAND_BUFFER: usize = 64 * 1024;
const MAX_USERS: usize = 16 * 1024;
const MAIN_ROOM_CAPACITY: u32 = 128;
const USER_ROOM_CAPACITY: u32 = 16;
const CONNECTION_IDLE: Duration = Duration::from_secs(120);

const NEWS: &str =
    "Welcome to NFSU1 browser Online.\nModify docs/online-protocol.md notes as needed.";
/// nfsuserver GetPlayerStat: 35 hex CSV fields (all/circ/sprint/drag/drift × 7).
const DEFAULT_STAT: &str = "3e8,a,2,0,1e240,1e240,3e8,3e8,a,2,0,1e240,1e240,3e8,3e8,a,2,0,1e240,1e240,3e8,3e8,a,2,0,1e240,1e240,3e8,3e8,a,2,0,1e240,1e240,3e8";
const SKEY: &str = "SKEY=$37940faf2a8d1381a3b7d0d2f570e6a7";

pub struct OnlineHost {
    conns: HashMap<ConnKey, Conn>,
    /// username → personas (max 4), in-memory "DB".
    users: HashMap<String, Vec<String>>,
    rooms: Vec<Room>,
    next_room_id: u32,
    next_user_id: u32,
    next_game_id: u32,
}

#[derive(Clone)]
struct Room {
    id: u32,
    name: String,
    host: String,
    count: u32,
    global: bool,
    members: Vec<ConnKey>,
    games: Vec<Game>,
}

impl Room {
    fn capacity(&self) -> u32 {
        if self.global {
            MAIN_ROOM_CAPACITY
        } else {
            USER_ROOM_CAPACITY
        }
    }
}

#[derive(Clone)]
struct Game {
    id: u32,
    name: String,
    params: String,
    max: u32,
    min: u32,
    sysflags: u32,
    members: Vec<ConnKey>,
}

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
struct ConnKey {
    peer: u32,
    sport: u16,
    dport: u16,
    cid: u32,
}

struct Conn {
    buf: Vec<u8>,
    user: Option<String>,
    persona: Option<String>,
    peer_ip: String,
    user_id: u32,
    car: String,
    room_id: Option<u32>,
    game_id: Option<u32>,
    last_active: Instant,
    last_ping: Option<Instant>,
    ping_seq: u32,
}

struct ConnInfo {
    persona: String,
    user: String,
    addr: String,
    uid: u32,
    car: String,
    game_id: u32,
}

impl OnlineHost {
    pub fn new() -> Self {
        let mut rooms = Vec::new();
        let mut id = 1u32;
        for prefix in b'A'..=b'H' {
            rooms.push(Room {
                id,
                name: format!("{}.Main Lobby", prefix as char),
                host: "nfsu1".into(),
                count: 0,
                global: true,
                members: Vec::new(),
                games: Vec::new(),
            });
            id += 1;
        }
        Self {
            conns: HashMap::new(),
            users: HashMap::new(),
            rooms,
            next_room_id: id,
            next_user_id: 1,
            next_game_id: 1,
        }
    }

    fn room_list_msgs(&self, peer: u32, sport: u16, dport: u16, cid: u32) -> Vec<Vec<u8>> {
        self.rooms
            .iter()
            .filter(|r| r.global || r.count > 0)
            .map(|r| {
                tcp_data(
                    peer,
                    dport,
                    sport,
                    cid,
                    &make_command(
                        "+rom",
                        &[
                            &format!("I={}", r.id),
                            &format!("N={}", r.name),
                            &format!("H={}", r.host),
                            "F=CK",
                            &format!("T={}", r.count),
                            &format!("L={}", r.capacity()),
                            "P=0",
                        ],
                    ),
                )
            })
            .collect()
    }

    pub fn on_frame(&mut self, frame: &[u8]) -> Vec<Vec<u8>> {
        if frame.len() < F_DATA + LAN_HDR {
            return Vec::new();
        }
        let kind = frame[0];
        let peer = u32::from_be_bytes(frame[4..8].try_into().unwrap());

        if kind == KIND_LAN_ICMP {
            return icmp_echo_reply(peer, &frame[F_DATA + LAN_HDR..]);
        }
        if kind != KIND_LAN_TCP {
            return Vec::new();
        }

        let sport = u16::from_be_bytes(frame[12..14].try_into().unwrap());
        let dport = u16::from_be_bytes(frame[14..16].try_into().unwrap());
        let op = frame[F_DATA];
        let cid = u32::from_le_bytes(frame[F_DATA + 4..F_DATA + 8].try_into().unwrap());
        let key = ConnKey {
            peer,
            sport,
            dport,
            cid,
        };

        match op {
            TCP_SYN => {
                if dport != PORT_REDIR
                    && dport != PORT_LOBBY
                    && dport != PORT_REPORT
                    && dport != PORT_CLIENT_REP
                {
                    return vec![tcp_ctl(peer, dport, sport, TCP_RST, cid)];
                }
                // A repeated SYN must not replace a live connection and leave
                // its old room/game membership behind.
                if self.conns.contains_key(&key) {
                    return vec![tcp_ctl(peer, dport, sport, TCP_SYNACK, cid)];
                }
                if self.conns.keys().filter(|k| k.peer == peer).count() >= MAX_PEER_CONNECTIONS {
                    return vec![tcp_ctl(peer, dport, sport, TCP_RST, cid)];
                }
                let peer_ip = std::net::Ipv4Addr::from(peer).to_string();
                let user_id = self.next_user_id;
                self.next_user_id = self.next_user_id.saturating_add(1);
                self.conns.insert(
                    key,
                    Conn {
                        buf: Vec::new(),
                        user: None,
                        persona: None,
                        peer_ip,
                        user_id,
                        car: String::new(),
                        room_id: None,
                        game_id: None,
                        last_active: Instant::now(),
                        last_ping: None,
                        ping_seq: 0,
                    },
                );
                vec![tcp_ctl(peer, dport, sport, TCP_SYNACK, cid)]
            }
            TCP_DATA => {
                let payload = &frame[F_DATA + LAN_HDR..];
                let Some(conn) = self.conns.get_mut(&key) else {
                    return vec![tcp_ctl(peer, dport, sport, TCP_RST, cid)];
                };
                if conn.buf.len().saturating_add(payload.len()) > MAX_COMMAND_BUFFER {
                    let mut out = self.close_connection(key);
                    out.push(tcp_ctl(peer, dport, sport, TCP_RST, cid));
                    return out;
                }
                conn.buf.extend_from_slice(payload);
                let mut cmds = Vec::new();
                while let Some(cmd) = take_command(&mut conn.buf) {
                    cmds.push(cmd);
                }
                if let Some(c) = self.conns.get_mut(&key) {
                    c.last_active = Instant::now();
                }
                let mut out = Vec::new();
                for cmd in cmds {
                    out.extend(self.handle_cmd(key, &cmd));
                }
                out
            }
            TCP_FIN | TCP_RST => {
                let mut out = self.close_connection(key);
                if op == TCP_FIN {
                    out.push(tcp_ctl(peer, dport, sport, TCP_FIN, cid));
                }
                out
            }
            _ => Vec::new(),
        }
    }

    /// Release every virtual socket owned by a disconnected browser before its
    /// address can be allocated to someone else.
    pub fn disconnect_peer(&mut self, peer: u32) -> Vec<Vec<u8>> {
        let keys: Vec<_> = self
            .conns
            .keys()
            .filter(|k| k.peer == peer)
            .copied()
            .collect();
        let mut out = Vec::new();
        for key in keys {
            out.extend(self.close_connection(key));
        }
        out.retain(|frame| u32::from_be_bytes(frame[8..12].try_into().unwrap()) != peer);
        out
    }

    fn close_connection(&mut self, key: ConnKey) -> Vec<Vec<u8>> {
        let room_id = self.conns.get(&key).and_then(|c| c.room_id);
        let games: Vec<u32> = room_id
            .and_then(|rid| self.rooms.iter().find(|r| r.id == rid))
            .map(|room| {
                room.games
                    .iter()
                    .filter(|g| g.members.contains(&key))
                    .map(|g| g.id)
                    .collect()
            })
            .unwrap_or_default();
        self.leave_room(key);
        self.conns.remove(&key);
        let Some(rid) = room_id else {
            return Vec::new();
        };
        let Some(room) = self.rooms.iter().find(|r| r.id == rid) else {
            return Vec::new();
        };
        let mut out = Vec::new();
        for gid in games {
            let fields = if let Some(game) = room.games.iter().find(|g| g.id == gid) {
                self.agm_fields(&room.name, game)
            } else {
                vec![format!("IDENT={gid}")]
            };
            let refs: Vec<_> = fields.iter().map(String::as_str).collect();
            out.extend(self.broadcast_room(rid, &make_command("+agm", &refs)));
        }
        let count = room.count;
        let remove_room = !room.global && count == 0;
        out.extend(self.broadcast_lobby(&make_command("+pop", &[&format!("Z={rid}/{count}")])));
        if remove_room {
            self.rooms.retain(|r| r.id != rid);
            out.extend(self.broadcast_lobby(&make_command("+rom", &[&format!("I={rid}")])));
        }
        out
    }

    pub fn keepalive_pings(&mut self) -> Vec<Vec<u8>> {
        let now = Instant::now();
        let mut out = Vec::new();
        let keys: Vec<ConnKey> = self.conns.keys().copied().collect();
        for key in keys {
            if self
                .conns
                .get(&key)
                .is_some_and(|c| now.duration_since(c.last_active) >= CONNECTION_IDLE)
            {
                out.extend(self.close_connection(key));
                out.push(tcp_ctl(key.peer, key.dport, key.sport, TCP_RST, key.cid));
                continue;
            }
            let Some(c) = self.conns.get_mut(&key) else {
                continue;
            };
            if key.dport != PORT_LOBBY && key.dport != PORT_REDIR {
                continue;
            }
            if now.duration_since(c.last_active) < Duration::from_secs(25) {
                continue;
            }
            if c.last_ping
                .map(|t| now.duration_since(t) < Duration::from_secs(20))
                .unwrap_or(false)
            {
                continue;
            }
            c.ping_seq = c.ping_seq.wrapping_add(1);
            let seq = c.ping_seq;
            c.last_ping = Some(now);
            let mut body = vec![0u8; 12];
            body[..4].copy_from_slice(b"~png");
            body[4..8].copy_from_slice(&seq.to_be_bytes());
            body[8..12].copy_from_slice(&12u32.to_be_bytes());
            out.push(tcp_data(key.peer, key.dport, key.sport, key.cid, &body));
        }
        out
    }

    fn handle_cmd(&mut self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let name = cmd_name(cmd);
        let peer = key.peer;
        let sport = key.sport;
        let dport = key.dport;
        let cid = key.cid;

        if !name.starts_with("~png") {
            let preview: String = cmd
                .get(12..)
                .unwrap_or(&[])
                .iter()
                .take(72)
                .map(|b| match *b {
                    0x20..=0x7e => *b as char,
                    9 | 10 => '|',
                    _ => '.',
                })
                .collect();
            eprintln!(
                "[online] << {name} {} :{}→{} ({}B) {preview}",
                std::net::Ipv4Addr::from(peer),
                sport,
                dport,
                cmd.len()
            );
        }

        if dport == PORT_REPORT || dport == PORT_CLIENT_REP {
            return Vec::new();
        }
        if dport == PORT_REDIR {
            return vec![tcp_data(
                peer,
                dport,
                sport,
                cid,
                &make_command(
                    "@dir",
                    &[
                        "ADDR=10.77.0.1",
                        "PORT=10901",
                        "SESS=1072010288",
                        "MASK=0295f3f70ecb1757cd7001b9a7a5eac8",
                    ],
                ),
            )];
        }

        if name.starts_with("~png") {
            if let Some(c) = self.conns.get_mut(&key) {
                c.last_active = Instant::now();
            }
            return Vec::new();
        }
        if name.starts_with("addr") || name.starts_with("skey") {
            return vec![tcp_data(
                peer,
                dport,
                sport,
                cid,
                &make_command("skey", &[SKEY]),
            )];
        }
        if name.starts_with("acct") {
            return self.handle_acct(key, cmd);
        }
        if name.starts_with("auth") {
            return self.handle_auth(key, cmd);
        }
        if name.starts_with("cper") {
            return self.handle_cper(key, cmd);
        }
        if name.starts_with("dper") {
            return self.handle_dper(key, cmd);
        }
        if name.starts_with("pers") {
            return self.handle_pers(key, cmd);
        }
        if name.starts_with("news") {
            return vec![tcp_data(
                peer,
                dport,
                sport,
                cid,
                &make_command("newsnew0", &[NEWS]),
            )];
        }
        if name.starts_with("auxi") {
            return self.handle_auxi(key, cmd);
        }
        if name.starts_with("sele") {
            let mut out = vec![tcp_data(
                peer,
                dport,
                sport,
                cid,
                &make_command(
                    "sele",
                    &[
                        "GAMES=1", "ROOMS=1", "USERS=1", "MESGS=1", "RANKS=0", "MORE=1", "SLOTS=36",
                    ],
                ),
            )];
            out.extend(self.room_list_msgs(peer, sport, dport, cid));
            return out;
        }
        if name.starts_with("user") {
            return self.handle_user(key);
        }
        if name.starts_with("room") {
            return self.handle_room(key, cmd);
        }
        if name.starts_with("move") {
            return self.handle_move(key, cmd);
        }
        if name.starts_with("mesg") {
            return self.handle_mesg(key, cmd);
        }
        if name.starts_with("gcre") {
            return self.handle_gcre(key, cmd);
        }
        if name.starts_with("gjoi") {
            return self.handle_gjoi(key, &field_at(cmd, 17).unwrap_or_default());
        }
        if name.starts_with("gget") {
            return self.handle_gget(key, &field_at(cmd, 17).unwrap_or_default());
        }
        if name.starts_with("glea") {
            return self.handle_glea(key, &field_at(cmd, 17).unwrap_or_default());
        }
        if name.starts_with("gdel") {
            return self.handle_gdel(key, &field_at(cmd, 17).unwrap_or_default());
        }
        if name.starts_with("gsta") {
            return self.handle_gsta(key, cmd);
        }
        if name.starts_with("snap") {
            return self.handle_snap(key, cmd);
        }
        if name.starts_with("rank") {
            return vec![tcp_data(
                peer,
                dport,
                sport,
                cid,
                &make_command("rank", &["RANK=Unranked", "TIME=866"]),
            )];
        }

        eprintln!("[online] unhandled {name:?} ({} bytes)", cmd.len());
        Vec::new()
    }

    fn reserve_user(&mut self, user: &str) -> bool {
        if self.users.contains_key(user) || self.users.len() < MAX_USERS {
            return true;
        }
        // Accounts are only an in-memory stand-in. Under pressure discard
        // inactive accounts, retaining every connected player's personas.
        let active: HashSet<_> = self.conns.values().filter_map(|c| c.user.clone()).collect();
        self.users.retain(|name, _| active.contains(name));
        self.users.len() < MAX_USERS
    }

    fn reset_connection(&mut self, key: ConnKey) -> Vec<Vec<u8>> {
        let mut out = self.close_connection(key);
        out.push(tcp_ctl(key.peer, key.dport, key.sport, TCP_RST, key.cid));
        out
    }

    fn handle_acct(&mut self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let uid = self.conns.get(&key).map(|c| c.user_id).unwrap_or(1);
        let user = extract_name(cmd).unwrap_or_else(|| format!("p{uid}"));
        if user.is_empty() || user.len() > 16 {
            return vec![tcp_data(
                key.peer,
                key.dport,
                key.sport,
                key.cid,
                &make_command("acctinam", &[]),
            )];
        }
        if self.users.contains_key(&user) {
            return vec![tcp_data(
                key.peer,
                key.dport,
                key.sport,
                key.cid,
                &make_command("acctdupl", &[]),
            )];
        }
        if !self.reserve_user(&user) {
            return self.reset_connection(key);
        }
        self.users.insert(user.clone(), Vec::new());
        if let Some(c) = self.conns.get_mut(&key) {
            c.user = Some(user.clone());
        }
        vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command("acct", &[&format!("NAME={user}"), "PERSONAS=", "AGE=24"]),
        )]
    }

    fn handle_auth(&mut self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let uid = self.conns.get(&key).map(|c| c.user_id).unwrap_or(1);
        let user = extract_name(cmd).unwrap_or_else(|| format!("p{uid}"));
        if !self.reserve_user(&user) {
            return self.reset_connection(key);
        }
        // The browser enters Online with the active profile's name. Keep
        // account and persona aligned without a separate persona selection.
        let default_persona = user.clone();
        let personas = self
            .users
            .entry(user.clone())
            .or_insert_with(|| vec![default_persona.clone()]);
        if personas.is_empty() {
            personas.push(default_persona.clone());
        }
        let pers = personas.join(",");
        if let Some(c) = self.conns.get_mut(&key) {
            c.user = Some(user.clone());
            if c.persona.is_none() {
                c.persona = personas.first().cloned();
            }
        }
        let mut out = vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command(
                "auth",
                &[
                    "TOS=1",
                    &format!("NAME={user}"),
                    "MAIL=nfsu1@local",
                    "BORN=19800325",
                    "GEND=M",
                    "FROM=US",
                    "LANG=en",
                    "SPAM=NN",
                    &format!("PERSONAS={pers}"),
                    "LAST=2003.12.8 15:51:38",
                ],
            ),
        )];
        out.extend(self.room_list_msgs(key.peer, key.sport, key.dport, key.cid));
        out
    }

    fn handle_cper(&mut self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let persona = extract_name(cmd).unwrap_or_else(|| "Player".into());
        if persona.is_empty() || persona.len() > 16 {
            return vec![tcp_data(
                key.peer,
                key.dport,
                key.sport,
                key.cid,
                &make_command("cperinam", &[]),
            )];
        }
        // Duplicate persona across any account.
        for list in self.users.values() {
            if list.iter().any(|p| p == &persona) {
                return vec![tcp_data(
                    key.peer,
                    key.dport,
                    key.sport,
                    key.cid,
                    &make_command("cperdupl", &[]),
                )];
            }
        }
        let Some(c) = self.conns.get(&key) else {
            return Vec::new();
        };
        let user = c.user.clone().unwrap_or_else(|| persona.clone());
        if !self.reserve_user(&user) {
            return self.reset_connection(key);
        }
        let list = self.users.entry(user.clone()).or_default();
        if list.len() >= 4 {
            return vec![tcp_data(
                key.peer,
                key.dport,
                key.sport,
                key.cid,
                &make_command("cperiper", &[]),
            )];
        }
        list.push(persona.clone());
        if let Some(c) = self.conns.get_mut(&key) {
            c.user = Some(user.clone());
            c.persona = Some(persona.clone());
        }
        vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command(
                "cper",
                &[&format!("NAME={user}"), &format!("PERS={persona}")],
            ),
        )]
    }

    fn handle_dper(&mut self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let persona = field_at(cmd, 17).unwrap_or_default();
        if let Some(c) = self.conns.get(&key) {
            if let Some(user) = c.user.clone() {
                if let Some(list) = self.users.get_mut(&user) {
                    list.retain(|p| p != &persona);
                }
            }
        }
        if let Some(c) = self.conns.get_mut(&key) {
            if c.persona.as_deref() == Some(persona.as_str()) {
                c.persona = None;
            }
        }
        vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command("dper", &[]),
        )]
    }

    fn handle_pers(&mut self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let persona = extract_name(cmd).unwrap_or_else(|| "Player".into());
        if let Some(c) = self.conns.get_mut(&key) {
            c.persona = Some(persona.clone());
        }
        vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command(
                "pers",
                &[
                    &format!("NAME={persona}"),
                    "PRES=1",
                    "PFLG=0",
                    "FLGS=0",
                    "ID=1",
                ],
            ),
        )]
    }

    fn handle_auxi(&mut self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let param = if cmd.len() > 12 {
            String::from_utf8_lossy(&cmd[12..]).into_owned()
        } else {
            String::new()
        };
        if let Some(c) = self.conns.get_mut(&key) {
            if cmd.len() > 17 {
                let car = String::from_utf8_lossy(&cmd[17..]);
                let end = car
                    .find(|c| c == '\0' || c == '\t' || c == '\n')
                    .unwrap_or(car.len());
                c.car = car[..end].to_string();
            }
        }
        vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command("auxi", &[&param]),
        )]
    }

    fn handle_user(&self, key: ConnKey) -> Vec<Vec<u8>> {
        let info = self.conn_info(key);
        vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command(
                "user",
                &[
                    &format!("PERS={}", info.persona),
                    "LAST=2004.6.1 15:57:52",
                    "EXPR=1072566000",
                    "STAT=",
                    "CHEAT=3",
                    "ACK_REP=186",
                    "REP=186",
                    "PLAST=2004.6.1 15:57:46",
                    "PSINCE=2003.11.25 07:56:09",
                    "DCNT=0",
                    &format!("ADDR={}", info.addr),
                    "SERV=10.77.0.1",
                    "RANK=99999",
                    "MESG=nfsu1",
                ],
            ),
        )]
    }

    fn handle_room(&mut self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let room_name = field_at(cmd, 17).unwrap_or_else(|| format!("Room{}", self.next_room_id));
        if room_name.is_empty() || self.rooms.iter().any(|r| r.name == room_name) {
            return vec![tcp_data(
                key.peer,
                key.dport,
                key.sport,
                key.cid,
                &make_command("roomroom", &[]),
            )];
        }
        let id = self.next_room_id;
        self.next_room_id = self.next_room_id.saturating_add(1);
        let info = self.conn_info(key);
        self.rooms.push(Room {
            id,
            name: room_name.clone(),
            host: info.persona.clone(),
            count: 0,
            global: false,
            members: Vec::new(),
            games: Vec::new(),
        });
        let mut out = Vec::new();
        out.push(tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command(
                "room",
                &[
                    &format!("IDENT={id}"),
                    &format!("NAME={room_name}"),
                    &format!("HOST={}", info.persona),
                    "DESC=",
                    "COUNT=1",
                    &format!("LIMIT={USER_ROOM_CAPACITY}"),
                    "FLAGS=C",
                ],
            ),
        ));
        out.push(self.who_packet(key, &info, &room_name, id));
        out.extend(self.add_user_to_room(key, id));
        out.push(tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command(
                "+msg",
                &[
                    "F=CU",
                    "T=\"has created the room\"",
                    &format!("N={}", info.persona),
                ],
            ),
        ));
        // Broadcast +rom (8 fields) to all lobby peers.
        let rom = make_command(
            "+rom",
            &[
                &format!("I={id}"),
                &format!("N={room_name}"),
                &format!("H={}", info.persona),
                "F=CH",
                "T=1",
                &format!("L={USER_ROOM_CAPACITY}"),
                "P=10",
                &format!("A={}", info.addr),
            ],
        );
        out.extend(self.broadcast_lobby(&rom));
        out.push(tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command(
                "+usr",
                &[
                    &format!("PI={}", info.uid),
                    &format!("N={}", info.persona),
                    &format!("M={}", info.user),
                    "F=HU",
                    &format!("A={}", info.addr),
                    "P=223",
                    &format!("S={DEFAULT_STAT}"),
                    &format!("X={}", info.car),
                    "G=0",
                    "T=1",
                ],
            ),
        ));
        out
    }

    fn handle_move(&mut self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let room_name = field_at(cmd, 17).unwrap_or_default();
        if let Some(id) = self
            .rooms
            .iter()
            .find(|r| r.name == room_name)
            .map(|r| r.id)
        {
            let mut out = self.add_user_to_room(key, id);
            if self.conns.get(&key).and_then(|c| c.room_id) != Some(id) {
                return out;
            }
            // +pop Z=id/count to all lobby users
            if let Some(room) = self.rooms.iter().find(|r| r.id == id) {
                let pop = make_command("+pop", &[&format!("Z={}/{}", room.id, room.count)]);
                out.extend(self.broadcast_lobby(&pop));
            }
            return out;
        }
        // Leave current room (move to missing).
        let left_id = self.conns.get(&key).and_then(|c| c.room_id);
        self.leave_room(key);
        let mut out = vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command(
                "move",
                &["IDENT=0", "NAME=", "COUNT=0", "LIDENT=0", "LCOUNT=0"],
            ),
        )];
        if let Some(id) = left_id {
            if let Some(room) = self.rooms.iter().find(|r| r.id == id) {
                let pop = make_command("+pop", &[&format!("Z={}/{}", room.id, room.count)]);
                out.extend(self.broadcast_lobby(&pop));
            }
            // Remove empty non-global rooms.
            if let Some(idx) = self
                .rooms
                .iter()
                .position(|r| r.id == id && !r.global && r.count == 0)
            {
                let rid = self.rooms[idx].id;
                self.rooms.remove(idx);
                let gone = make_command("+rom", &[&format!("I={rid}")]);
                out.extend(self.broadcast_lobby(&gone));
            }
        }
        out
    }

    fn handle_mesg(&mut self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let info = self.conn_info(key);
        let mut out = vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command("mesg", &[]),
        )];
        let fields = parse_kv_fields(cmd);
        let text = fields
            .get("TEXT")
            .cloned()
            .or_else(|| field_at(cmd, 17))
            .unwrap_or_default();
        // ATTR is a Dirtysock flag string, not a number. Speed.exe sends E0 for
        // an invite and E1 for a refusal; GAME/PARAMS are nested inside TEXT and
        // escaped one extra time. Relay that TEXT verbatim as T so the client
        // decodes each level itself. +msg reads F (not ATTR) and T (not GAME).
        let attr = fields.get("ATTR").map(String::as_str).unwrap_or("E");
        let is_challenge = attr.bytes().any(|b| matches!(b, b'0' | b'1'));

        let target = fields.get("PRIV").cloned().or_else(|| {
            let body = String::from_utf8_lossy(cmd.get(17..).unwrap_or(&[]));
            body.split(|c| c == '\t' || c == '\n' || c == '\0')
                .skip(1)
                .find_map(|p| p.strip_prefix("PRIV=").map(|s| s.to_string()))
                .or_else(|| {
                    let parts: Vec<_> = body
                        .split(|c| c == '\t' || c == '\n' || c == '\0')
                        .filter(|s| !s.is_empty())
                        .collect();
                    if parts.len() >= 2 && parts[1].starts_with("PRIV") {
                        parts.get(2).map(|s| (*s).to_string())
                    } else {
                        None
                    }
                })
        });

        if let Some(target) = target {
            if let Some(tk) = self.find_conn_by_name(&target) {
                let ti = self.conn_info(tk);
                out.push(tcp_data(
                    tk.peer,
                    tk.dport,
                    tk.sport,
                    tk.cid,
                    &make_command(
                        "+msg",
                        &[
                            &format!("F={attr}P"),
                            &format!("T={text}"),
                            &format!("N={}", info.persona),
                        ],
                    ),
                ));
                if is_challenge {
                    eprintln!("[online] challenge → {target} ATTR={attr}");
                } else {
                    // Only ordinary chat has a sender echo. Replaying an invite
                    // or refusal to its sender runs the wrong frontend action.
                    out.push(tcp_data(
                        key.peer,
                        key.dport,
                        key.sport,
                        key.cid,
                        &make_command(
                            "+msg",
                            &[
                                "F=EP5",
                                &format!("T={}: {text}", ti.persona),
                                &format!("N={}", info.persona),
                            ],
                        ),
                    ));
                }
            } else {
                eprintln!("[online] mesg PRIV={target}: user not found");
            }
        } else if let Some(rid) = self.conns.get(&key).and_then(|c| c.room_id) {
            let msg = make_command(
                "+msg",
                &["F=U", &format!("T={text}"), &format!("N={}", info.persona)],
            );
            out.extend(self.broadcast_room(rid, &msg));
        }
        out
    }

    fn handle_gcre(&mut self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let fields = parse_kv_fields(cmd);
        let parsed = parse_gcre_fields(cmd, &fields);
        let game_name = parsed.name;
        let room_name = parsed.room;
        let max = parsed.max;
        let min = parsed.min;
        let sysflags = parsed.sysflags;
        let mut params = parsed.params;

        let room_id = self.conns.get(&key).and_then(|c| c.room_id).or_else(|| {
            self.rooms
                .iter()
                .find(|r| r.name == room_name)
                .map(|r| r.id)
        });
        let Some(room_id) = room_id else {
            eprintln!("[online] gcre with no room for {game_name}");
            return Vec::new();
        };
        let Some(room_idx) = self.rooms.iter().position(|r| r.id == room_id) else {
            return Vec::new();
        };
        let rname = self.rooms[room_idx].name.clone();
        let host_info = self.conn_info(key);
        if params.trim().is_empty() {
            // Challenge Settings FE skipped / empty PARAMS → client errors (gpar) mid-load.
            // Speed.exe builds PARAMS as TRACK=%d DIR=%d LAPS=%d MYIP=%d (≤300).
            let myip = ipv4_to_u32(&host_info.addr).unwrap_or(key.peer);
            params = default_params_for_room(&rname, myip);
            eprintln!(
                "[online] gcre empty PARAMS → default {params:?} (room {rname}; mode is room letter A–H)"
            );
        } else if params.len() > 300 {
            eprintln!(
                "[online] gcre PARAMS len {} > 300, truncating",
                params.len()
            );
            params.truncate(300);
        } else {
            eprintln!(
                "[online] gcre NAME={game_name} MAX={max} PARAMS_len={} PARAMS={params}",
                params.len()
            );
        }

        let gid = self.next_game_id;
        self.next_game_id = self.next_game_id.saturating_add(1);
        self.rooms[room_idx].games.push(Game {
            id: gid,
            name: game_name.clone(),
            params,
            max,
            min,
            sysflags,
            members: vec![key],
        });
        if let Some(c) = self.conns.get_mut(&key) {
            c.game_id = Some(gid);
        }
        let info = self.conn_info(key);
        let g = self.rooms[room_idx]
            .games
            .iter()
            .find(|g| g.id == gid)
            .cloned()
            .unwrap();
        let agm = self.agm_fields(&rname, &g);
        let agm_refs: Vec<&str> = agm.iter().map(|s| s.as_str()).collect();
        let members = self.rooms[room_idx].members.clone();
        let mut out = Vec::new();
        out.push(tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command("gjoi", &agm_refs),
        ));
        for to in &members {
            out.push(self.usr_packet(*to, &info, "H", "211", "2"));
        }
        out.push(tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command("gcre", &agm_refs),
        ));
        let agm_body = make_command("+agm", &agm_refs);
        out.extend(self.broadcast_room(room_id, &agm_body));
        // Accept/Refuse comes from the client's follow-up mesg (GAME+PARAMS), not a
        // synthetic F=EP5 chat dump of those fields.

        if g.members.len() as u32 >= g.max {
            if let Some(gi) = self.rooms[room_idx].games.iter().position(|x| x.id == gid) {
                out.extend(self.start_game(room_idx, gi));
            }
        }
        out
    }

    fn handle_gjoi(&mut self, key: ConnKey, game_name: &str) -> Vec<Vec<u8>> {
        let Some((room_idx, gidx)) = self.find_game_in_conn_room(key, game_name) else {
            return Vec::new();
        };
        if !self.rooms[room_idx].games[gidx].members.contains(&key) {
            self.rooms[room_idx].games[gidx].members.push(key);
        }
        let gid = self.rooms[room_idx].games[gidx].id;
        if let Some(c) = self.conns.get_mut(&key) {
            c.game_id = Some(gid);
        }
        let room_id = self.rooms[room_idx].id;
        let rname = self.rooms[room_idx].name.clone();
        let g = self.rooms[room_idx].games[gidx].clone();
        let info = self.conn_info(key);
        let agm = self.agm_fields(&rname, &g);
        let agm_refs: Vec<&str> = agm.iter().map(|s| s.as_str()).collect();
        let filled = g.members.len() as u32 >= g.max;
        let mut out = vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command("gjoi", &agm_refs),
        )];
        for to in &self.rooms[room_idx].members.clone() {
            out.push(self.usr_packet(*to, &info, "H", "211", "2"));
        }
        let agm_body = make_command("+agm", &agm_refs);
        out.extend(self.broadcast_room(room_id, &agm_body));
        if filled {
            out.extend(self.start_game(room_idx, gidx));
        }
        out
    }

    fn handle_gget(&self, key: ConnKey, game_name: &str) -> Vec<Vec<u8>> {
        let Some((room_idx, gidx)) = self.find_game_in_conn_room(key, game_name) else {
            return Vec::new();
        };
        let rname = self.rooms[room_idx].name.clone();
        let g = &self.rooms[room_idx].games[gidx];
        let agm = self.agm_fields(&rname, g);
        let refs: Vec<&str> = agm.iter().map(|s| s.as_str()).collect();
        vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command("gget", &refs),
        )]
    }

    fn handle_glea(&mut self, key: ConnKey, game_name: &str) -> Vec<Vec<u8>> {
        let Some((room_idx, gidx)) = self.find_game_in_conn_room(key, game_name) else {
            return Vec::new();
        };
        self.remove_from_game(room_idx, gidx, key)
    }

    fn handle_gdel(&mut self, key: ConnKey, game_name: &str) -> Vec<Vec<u8>> {
        let Some((room_idx, gidx)) = self.find_game_in_conn_room(key, game_name) else {
            return Vec::new();
        };
        let room_id = self.rooms[room_idx].id;
        let gid = self.rooms[room_idx].games[gidx].id;
        let members = self.rooms[room_idx].games[gidx].members.clone();
        for mk in &members {
            if let Some(c) = self.conns.get_mut(mk) {
                c.game_id = None;
            }
            let info = self.conn_info(*mk);
            for to in &self.rooms[room_idx].members.clone() {
                // refresh will be sent below via packets
                let _ = (to, &info);
            }
        }
        self.rooms[room_idx].games.remove(gidx);
        let mut out = vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command("gdel", &[]),
        )];
        for mk in &members {
            let info = self.conn_info(*mk);
            for to in &self.rooms[room_idx].members.clone() {
                out.push(self.usr_packet(*to, &info, "H", "211", "2"));
            }
        }
        let gone = make_command("+agm", &[&format!("IDENT={gid}")]);
        out.extend(self.broadcast_room(room_id, &gone));
        out
    }

    fn handle_gsta(&mut self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let game_name = field_at(cmd, 17).unwrap_or_default();
        let Some((room_idx, gidx)) = self.find_game_in_conn_room(key, &game_name) else {
            return vec![tcp_data(
                key.peer,
                key.dport,
                key.sport,
                key.cid,
                &make_command("gstanepl", &[]),
            )];
        };
        let min = self.rooms[room_idx].games[gidx].min;
        let count = self.rooms[room_idx].games[gidx].members.len() as u32;
        if count < min {
            return vec![tcp_data(
                key.peer,
                key.dport,
                key.sport,
                key.cid,
                &make_command("gstanepl", &[]),
            )];
        }
        let mut out = vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command("gsta", &[""]),
        )];
        out.extend(self.start_game(room_idx, gidx));
        out
    }

    fn handle_snap(&self, key: ConnKey, cmd: &[u8]) -> Vec<Vec<u8>> {
        let fields = parse_kv_fields(cmd);
        let index: u32 = fields
            .get("INDEX")
            .and_then(|s| s.parse().ok())
            .or_else(|| field_at(cmd, 18).and_then(|s| s.parse().ok()))
            .unwrap_or(1);
        let chan: u32 = fields.get("CHAN").and_then(|s| s.parse().ok()).unwrap_or(0);
        let start: u32 = fields
            .get("START")
            .and_then(|s| s.parse().ok())
            .unwrap_or(0);
        let range: u32 = fields
            .get("RANGE")
            .and_then(|s| s.parse().ok())
            .unwrap_or(100);

        let mut out = vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command(
                "snap",
                &[
                    &format!("INDEX={index}"),
                    &format!("CHAN={chan}"),
                    &format!("START={start}"),
                    &format!("RANGE={range}"),
                    "SEQN=0",
                ],
            ),
        )];

        // Hardcoded leaderboard stand-ins (indices 1–5 = overall / modes).
        let fake = [("Racer1", 1u32), ("Racer2", 2u32), ("nfsu1", 3u32)];
        for (name, ind) in fake {
            let s = match index {
                1 => format!("S={ind:x},a,2,0,1e240,1e240,3e8"),
                2 => format!("S=,,,,,,,{ind:x},a,2,0,1e240,1e240,3e8"),
                3 => format!("S=,,,,,,,,,,,,,,{ind:x},a,2,0,1e240,1e240,3e8"),
                4 => format!("S=,,,,,,,,,,,,,,,,,,,,,{ind:x},a,2,0,1e240,1e240,3e8"),
                5 => format!("S=,,,,,,,,,,,,,,,,,,,,,,,,,,,,{ind:x},a,2,0,1e240,1e240,3e8"),
                _ => format!("S={ind:x},0,0"), // track stars stub
            };
            out.push(tcp_data(
                key.peer,
                key.dport,
                key.sport,
                key.cid,
                &make_command("+snp", &[&format!("N={name}"), &s]),
            ));
        }
        out
    }

    fn start_game(&self, room_idx: usize, gidx: usize) -> Vec<Vec<u8>> {
        let room = &self.rooms[room_idx];
        let g = &room.games[gidx];
        let rname = room.name.clone();
        let seed: u32 = rand::random();
        let agm = self.agm_fields(&rname, g);
        let mut out = Vec::new();
        for mk in &g.members {
            let mi = self.conn_info(*mk);
            let mut fields = agm.clone();
            fields.push(format!("SEED={seed}"));
            fields.push(format!("SELF={}", mi.persona));
            let refs: Vec<&str> = fields.iter().map(|s| s.as_str()).collect();
            out.push(tcp_data(
                mk.peer,
                mk.dport,
                mk.sport,
                mk.cid,
                &make_command("+ses", &refs),
            ));
        }
        let agm_refs: Vec<&str> = agm.iter().map(|s| s.as_str()).collect();
        let body = make_command("+agm", &agm_refs);
        out.extend(self.broadcast_room(room.id, &body));
        out
    }

    fn remove_from_game(&mut self, room_idx: usize, gidx: usize, key: ConnKey) -> Vec<Vec<u8>> {
        let room_id = self.rooms[room_idx].id;
        let rname = self.rooms[room_idx].name.clone();
        self.rooms[room_idx].games[gidx]
            .members
            .retain(|k| *k != key);
        if let Some(c) = self.conns.get_mut(&key) {
            c.game_id = None;
        }
        let info = self.conn_info(key);
        let mut out = Vec::new();
        for to in &self.rooms[room_idx].members.clone() {
            out.push(self.usr_packet(*to, &info, "H", "211", "2"));
        }
        if self.rooms[room_idx].games[gidx].members.is_empty() {
            let gid = self.rooms[room_idx].games[gidx].id;
            self.rooms[room_idx].games.remove(gidx);
            let gone = make_command("+agm", &[&format!("IDENT={gid}")]);
            out.extend(self.broadcast_room(room_id, &gone));
        } else {
            let g = self.rooms[room_idx].games[gidx].clone();
            let agm = self.agm_fields(&rname, &g);
            let refs: Vec<&str> = agm.iter().map(|s| s.as_str()).collect();
            out.push(tcp_data(
                key.peer,
                key.dport,
                key.sport,
                key.cid,
                &make_command("glea", &refs),
            ));
            let body = make_command("+agm", &refs);
            out.extend(self.broadcast_room(room_id, &body));
        }
        out
    }

    fn add_user_to_room(&mut self, key: ConnKey, room_id: u32) -> Vec<Vec<u8>> {
        let Some(room_idx) = self.rooms.iter().position(|r| r.id == room_id) else {
            return Vec::new();
        };
        let room = &self.rooms[room_idx];
        if room.members.len() >= room.capacity() as usize && !room.members.contains(&key) {
            return vec![tcp_data(
                key.peer,
                key.dport,
                key.sport,
                key.cid,
                &make_command("movefull", &[]),
            )];
        }
        // Check capacity before leaving: a failed move must preserve the
        // player's current room and any race membership.
        self.leave_room(key);
        let count_before = self.rooms[room_idx].members.len() as u32;
        let rname = self.rooms[room_idx].name.clone();
        let rid = self.rooms[room_idx].id;
        let members = self.rooms[room_idx].members.clone();

        let mut out = vec![tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command(
                "move",
                &[
                    &format!("IDENT={rid}"),
                    &format!("NAME={rname}"),
                    &format!("COUNT={count_before}"),
                    "FLAGS=C",
                ],
            ),
        )];

        self.rooms[room_idx].members.push(key);
        self.rooms[room_idx].count = self.rooms[room_idx].members.len() as u32;
        if let Some(c) = self.conns.get_mut(&key) {
            c.room_id = Some(rid);
        }

        let info = self.conn_info(key);
        out.push(self.who_packet(key, &info, &rname, rid));

        let refresh_targets = self.rooms[room_idx].members.clone();
        for to in &refresh_targets {
            out.push(self.usr_packet(*to, &info, "H", "211", "2"));
        }
        for mk in &members {
            let minfo = self.conn_info(*mk);
            out.push(self.usr_packet(key, &minfo, "H", "211", "2"));
        }
        out.push(self.usr_packet(key, &info, "H", "211", "2"));

        let games = self.rooms[room_idx].games.clone();
        for g in &games {
            if g.members.is_empty() {
                continue;
            }
            let agm = self.agm_fields(&rname, g);
            let refs: Vec<&str> = agm.iter().map(|s| s.as_str()).collect();
            out.push(tcp_data(
                key.peer,
                key.dport,
                key.sport,
                key.cid,
                &make_command("+agm", &refs),
            ));
        }
        out
    }

    fn leave_room(&mut self, key: ConnKey) {
        let Some(rid) = self.conns.get(&key).and_then(|c| c.room_id) else {
            return;
        };
        if let Some(c) = self.conns.get_mut(&key) {
            c.room_id = None;
            c.game_id = None;
        }
        if let Some(room) = self.rooms.iter_mut().find(|r| r.id == rid) {
            room.members.retain(|k| *k != key);
            room.count = room.members.len() as u32;
            for g in &mut room.games {
                g.members.retain(|k| *k != key);
            }
            room.games.retain(|g| !g.members.is_empty());
        }
    }

    fn find_game_in_conn_room(&self, key: ConnKey, game_name: &str) -> Option<(usize, usize)> {
        let room_id = self.conns.get(&key)?.room_id?;
        let room_idx = self.rooms.iter().position(|r| r.id == room_id)?;
        if self.rooms[room_idx].games.is_empty() {
            return None;
        }
        if game_name.is_empty() {
            return Some((room_idx, 0));
        }
        let gidx = self.rooms[room_idx]
            .games
            .iter()
            .position(|g| g.name == game_name)?;
        Some((room_idx, gidx))
    }

    fn find_conn_by_name(&self, name: &str) -> Option<ConnKey> {
        self.conns.iter().find_map(|(k, c)| {
            if c.user.as_deref() == Some(name) || c.persona.as_deref() == Some(name) {
                Some(*k)
            } else {
                None
            }
        })
    }

    fn broadcast_lobby(&self, payload: &[u8]) -> Vec<Vec<u8>> {
        self.conns
            .keys()
            .filter(|k| k.dport == PORT_LOBBY)
            .map(|k| tcp_data(k.peer, k.dport, k.sport, k.cid, payload))
            .collect()
    }

    fn broadcast_room(&self, room_id: u32, payload: &[u8]) -> Vec<Vec<u8>> {
        let Some(room) = self.rooms.iter().find(|r| r.id == room_id) else {
            return Vec::new();
        };
        room.members
            .iter()
            .map(|k| tcp_data(k.peer, k.dport, k.sport, k.cid, payload))
            .collect()
    }

    fn conn_info(&self, key: ConnKey) -> ConnInfo {
        self.conns
            .get(&key)
            .map(|c| ConnInfo {
                persona: c
                    .persona
                    .clone()
                    .or_else(|| c.user.clone())
                    .unwrap_or_else(|| "Player".into()),
                user: c.user.clone().unwrap_or_else(|| "Player".into()),
                addr: c.peer_ip.clone(),
                uid: c.user_id,
                car: c.car.clone(),
                game_id: c.game_id.unwrap_or(0),
            })
            .unwrap_or_else(|| ConnInfo {
                persona: "Player".into(),
                user: "Player".into(),
                addr: std::net::Ipv4Addr::from(key.peer).to_string(),
                uid: 1,
                car: String::new(),
                game_id: 0,
            })
    }

    fn who_packet(&self, key: ConnKey, info: &ConnInfo, room: &str, room_id: u32) -> Vec<u8> {
        tcp_data(
            key.peer,
            key.dport,
            key.sport,
            key.cid,
            &make_command(
                "+who",
                &[
                    &format!("I={}", info.uid),
                    &format!("N={}", info.persona),
                    &format!("M={}", info.user),
                    "F=",
                    &format!("A={}", info.addr),
                    &format!("S={DEFAULT_STAT}"),
                    &format!("X={}", info.car),
                    &format!("R={room}"),
                    &format!("RI={room_id}"),
                    "RF=C",
                    "RT=1",
                ],
            ),
        )
    }

    fn usr_packet(
        &self,
        to: ConnKey,
        info: &ConnInfo,
        flags: &str,
        port: &str,
        t: &str,
    ) -> Vec<u8> {
        tcp_data(
            to.peer,
            to.dport,
            to.sport,
            to.cid,
            &make_command(
                "+usr",
                &[
                    &format!("I={}", info.uid),
                    &format!("N={}", info.persona),
                    &format!("M={}", info.user),
                    &format!("F={flags}"),
                    &format!("A={}", info.addr),
                    &format!("P={port}"),
                    &format!("S={DEFAULT_STAT}"),
                    &format!("X={}", info.car),
                    &format!("G={}", info.game_id),
                    &format!("T={t}"),
                ],
            ),
        )
    }

    fn agm_fields(&self, room: &str, g: &Game) -> Vec<String> {
        let host = g
            .members
            .first()
            .map(|k| self.conn_info(*k).persona)
            .unwrap_or_else(|| "Player".into());
        let mut fields = vec![
            format!("IDENT={}", g.id),
            "WHEN=2003.12.8 15:52:54".into(),
            format!("NAME={}", g.name),
            format!("HOST={host}"),
            format!("PARAMS={}", g.params),
            format!("ROOM={room}"),
            format!("MAXSIZE={}", g.max),
            format!("MINSIZE={}", g.min),
            format!("COUNT={}", g.members.len()),
            "USERFLAGS=0".into(),
            format!("SYSFLAGS={}", g.sysflags),
        ];
        for (i, mk) in g.members.iter().enumerate() {
            let mi = self.conn_info(*mk);
            fields.push(format!("OPID{i}={}", mi.uid));
            fields.push(format!("OPPO{i}={}", mi.persona));
            fields.push(format!("ADDR{i}={}", mi.addr));
        }
        fields
    }
}

fn parse_kv_fields(cmd: &[u8]) -> HashMap<String, String> {
    let mut map = HashMap::new();
    if cmd.len() <= 12 {
        return map;
    }
    let text = String::from_utf8_lossy(&cmd[12..]);
    for part in text.split(|c| c == '\t' || c == '\0' || c == '\n' || c == '\r') {
        let p = part.trim();
        if p.is_empty() {
            continue;
        }
        if let Some((k, v)) = p.split_once('=') {
            map.insert(k.to_string(), v.to_string());
        }
    }
    map
}

struct GcreFields {
    name: String,
    room: String,
    max: u32,
    min: u32,
    sysflags: u32,
    params: String,
}

/// Prefer KEY= fields; fall back to nfsuserver positional skips after NAME=.
fn parse_gcre_fields(cmd: &[u8], fields: &HashMap<String, String>) -> GcreFields {
    let name = fields
        .get("NAME")
        .cloned()
        .or_else(|| field_at(cmd, 17))
        .unwrap_or_else(|| "Challenge".into());
    let room = fields.get("ROOM").cloned().unwrap_or_default();
    let max = fields
        .get("MAXSIZE")
        .and_then(|s| s.parse().ok())
        .unwrap_or(4);
    let min = fields
        .get("MINSIZE")
        .and_then(|s| s.parse().ok())
        .unwrap_or(2);
    let sysflags = fields
        .get("SYSFLAGS")
        .and_then(|s| s.parse().ok())
        .unwrap_or(0);
    let mut params = fields.get("PARAMS").cloned().unwrap_or_default();

    // Positional (nfsuserver): NAME@+17, then ROOM=/MAXSIZE=/MINSIZE=/SYSFLAGS=/PARAMS=
    // with fixed key-width skips. Used when KV missed PARAMS (odd separators).
    if params.is_empty() && cmd.len() > 17 {
        if let Some(pos) = parse_gcre_positional(cmd) {
            if !pos.params.is_empty() {
                params = pos.params;
            }
            return GcreFields {
                name: if name.is_empty() { pos.name } else { name },
                room: if room.is_empty() { pos.room } else { room },
                max: if fields.contains_key("MAXSIZE") {
                    max
                } else {
                    pos.max
                },
                min: if fields.contains_key("MINSIZE") {
                    min
                } else {
                    pos.min
                },
                sysflags: if fields.contains_key("SYSFLAGS") {
                    sysflags
                } else {
                    pos.sysflags
                },
                params,
            };
        }
    }
    GcreFields {
        name,
        room,
        max,
        min,
        sysflags,
        params,
    }
}

fn parse_gcre_positional(cmd: &[u8]) -> Option<GcreFields> {
    // Mirror nfsuserver.cpp gcre: null-terminate at each sep, skip key widths.
    let body = cmd.get(17..)?;
    let text = String::from_utf8_lossy(body);
    let seps: Vec<usize> = text
        .char_indices()
        .filter_map(|(i, c)| {
            if c == '\t' || c == '\n' || c == '\0' {
                Some(i)
            } else {
                None
            }
        })
        .collect();
    if seps.is_empty() {
        return None;
    }
    let name = text[..seps[0]].to_string();
    // After name sep: skip "ROOM=" (5) — nfsuserver does tmp += 6 from sep char.
    let mut cursor = seps[0] + 1;
    let skip_key = |s: &str, key: &str, cur: usize| -> Option<usize> {
        let rest = s.get(cur..)?;
        if rest.starts_with(key) {
            Some(cur + key.len())
        } else {
            // nfsuserver assumes the key is present and skips its fixed width
            Some(cur + key.len())
        }
    };
    cursor = skip_key(&text, "ROOM=", cursor)?;
    let room_end = text[cursor..]
        .find(|c| c == '\t' || c == '\n' || c == '\0')
        .map(|i| cursor + i)?;
    let room = text[cursor..room_end].to_string();
    cursor = room_end + 1;
    cursor = skip_key(&text, "MAXSIZE=", cursor)?;
    let max_end = text[cursor..]
        .find(|c| c == '\t' || c == '\n' || c == '\0')
        .map(|i| cursor + i)?;
    let max = text[cursor..max_end].parse().unwrap_or(4);
    cursor = max_end + 1;
    cursor = skip_key(&text, "MINSIZE=", cursor)?;
    let min_end = text[cursor..]
        .find(|c| c == '\t' || c == '\n' || c == '\0')
        .map(|i| cursor + i)?;
    let min = text[cursor..min_end].parse().unwrap_or(2);
    cursor = min_end + 1;
    cursor = skip_key(&text, "SYSFLAGS=", cursor)?;
    let sys_end = text[cursor..]
        .find(|c| c == '\t' || c == '\n' || c == '\0')
        .map(|i| cursor + i)?;
    let sysflags = text[cursor..sys_end].parse().unwrap_or(0);
    cursor = sys_end + 1;
    cursor = skip_key(&text, "PARAMS=", cursor)?;
    let params = text[cursor..]
        .trim_end_matches(|c| c == '\0' || c == '\t' || c == '\n' || c == '\r')
        .to_string();
    Some(GcreFields {
        name,
        room,
        max,
        min,
        sysflags,
        params,
    })
}

fn ipv4_to_u32(s: &str) -> Option<u32> {
    let mut parts = s.split('.');
    let a: u8 = parts.next()?.parse().ok()?;
    let b: u8 = parts.next()?.parse().ok()?;
    let c: u8 = parts.next()?.parse().ok()?;
    let d: u8 = parts.next()?.parse().ok()?;
    if parts.next().is_some() {
        return None;
    }
    Some(u32::from_be_bytes([a, b, c, d]))
}

/// Room letter selects mode; Challenge Settings normally picks track/laps.
/// Speed.exe stores PARAMS URL-encoded with `%0a` between keys (`TRACK%3d…`).
fn default_params_for_room(room: &str, myip: u32) -> String {
    let letter = room.chars().next().unwrap_or('E').to_ascii_uppercase();
    // Tracks/STREAM* IDs: 1001+ circuit, 1102+ sprint, 1201+ drag, 1301+ drift.
    let (track, laps) = match letter {
        'A' | 'E' => (1001u32, 3u32), // Circuit
        'B' | 'F' => (1102, 0),       // Sprint
        'C' | 'G' => (1301, 0),       // Drift
        'D' | 'H' => (1201, 0),       // Drag
        _ => (1001, 3),
    };
    format!("TRACK%3d{track}%0aDIR%3d0%0aLAPS%3d{laps}%0aMYIP%3d{myip}")
}

fn icmp_echo_reply(peer: u32, payload: &[u8]) -> Vec<Vec<u8>> {
    if payload.is_empty() || payload[0] != 8 {
        return Vec::new();
    }
    let mut rep = payload.to_vec();
    rep[0] = 0;
    let mut f = vec![0u8; F_DATA + LAN_HDR + rep.len()];
    f[0] = KIND_LAN_ICMP;
    f[4..8].copy_from_slice(&ONLINE_VIP.to_be_bytes());
    f[8..12].copy_from_slice(&peer.to_be_bytes());
    f[F_DATA] = 0;
    f[F_DATA + 1] = 64;
    f[F_DATA + LAN_HDR..].copy_from_slice(&rep);
    vec![f]
}

pub fn server_peer_json() -> serde_json::Value {
    serde_json::json!({
        "vip": ONLINE_VIP,
        "name": "nfsu1",
        "server": true,
    })
}

fn tcp_ctl(peer: u32, sport: u16, dport: u16, op: u8, cid: u32) -> Vec<u8> {
    let mut f = vec![0u8; F_DATA + LAN_HDR];
    f[0] = KIND_LAN_TCP;
    f[4..8].copy_from_slice(&ONLINE_VIP.to_be_bytes());
    f[8..12].copy_from_slice(&peer.to_be_bytes());
    f[12..14].copy_from_slice(&sport.to_be_bytes());
    f[14..16].copy_from_slice(&dport.to_be_bytes());
    f[F_DATA] = op;
    f[F_DATA + 1] = 64;
    f[F_DATA + 4..F_DATA + 8].copy_from_slice(&cid.to_le_bytes());
    f
}

fn tcp_data(peer: u32, sport: u16, dport: u16, cid: u32, payload: &[u8]) -> Vec<u8> {
    let mut f = tcp_ctl(peer, sport, dport, TCP_DATA, cid);
    f.extend_from_slice(payload);
    f
}

fn make_command(command: &str, params: &[&str]) -> Vec<u8> {
    let mut buf = vec![0u8; 12];
    let cmd = command.as_bytes();
    let n = cmd.len().min(12);
    buf[..n].copy_from_slice(&cmd[..n]);
    let mut len = 12usize;
    for (i, p) in params.iter().enumerate() {
        buf.extend_from_slice(p.as_bytes());
        buf.push(if i + 1 == params.len() { 0 } else { 9 });
        len = buf.len();
    }
    buf[8] = (len >> 24) as u8;
    buf[9] = (len >> 16) as u8;
    buf[10] = (len >> 8) as u8;
    buf[11] = len as u8;
    debug_assert_eq!(buf.len(), len);
    buf
}

fn take_command(buf: &mut Vec<u8>) -> Option<Vec<u8>> {
    if buf.len() < 12 {
        return None;
    }
    let req = u32::from_be_bytes(buf[8..12].try_into().ok()?) as usize;
    if !(12..=8192).contains(&req) {
        buf.clear();
        return None;
    }
    if buf.len() < req {
        return None;
    }
    Some(buf.drain(..req).collect())
}

fn cmd_name(cmd: &[u8]) -> String {
    let end = cmd
        .iter()
        .take(12)
        .position(|&b| b == 0)
        .unwrap_or(12.min(cmd.len()));
    String::from_utf8_lossy(&cmd[..end]).into_owned()
}

fn extract_name(cmd: &[u8]) -> Option<String> {
    if cmd.len() <= 12 {
        return None;
    }
    let body = &cmd[12..];
    let text = String::from_utf8_lossy(body);
    for part in text.split(|c| c == '\t' || c == '\0' || c == '\n' || c == '\r') {
        let p = part.trim();
        if let Some(v) = p.strip_prefix("NAME=") {
            if !v.is_empty() {
                return Some(v.to_string());
            }
        }
        if let Some(v) = p.strip_prefix("PERS=") {
            if !v.is_empty() {
                return Some(v.to_string());
            }
        }
    }
    field_at(cmd, 17).or_else(|| field_at(cmd, 12))
}

fn field_at(cmd: &[u8], off: usize) -> Option<String> {
    if cmd.len() <= off {
        return None;
    }
    let body = &cmd[off..];
    let end = body
        .iter()
        .position(|&b| b == 0 || b == 9 || b == 10 || b == 13)
        .unwrap_or(body.len());
    let s = String::from_utf8_lossy(&body[..end]).trim().to_string();
    if s.is_empty() || s.contains('=') {
        None
    } else {
        Some(s)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lan_tcp(peer: u32, sport: u16, dport: u16, op: u8, cid: u32, payload: &[u8]) -> Vec<u8> {
        let mut f = vec![0u8; F_DATA + LAN_HDR];
        f[0] = KIND_LAN_TCP;
        f[4..8].copy_from_slice(&peer.to_be_bytes());
        f[8..12].copy_from_slice(&ONLINE_VIP.to_be_bytes());
        f[12..14].copy_from_slice(&sport.to_be_bytes());
        f[14..16].copy_from_slice(&dport.to_be_bytes());
        f[F_DATA] = op;
        f[F_DATA + 1] = 64;
        f[F_DATA + 4..F_DATA + 8].copy_from_slice(&cid.to_le_bytes());
        f.extend_from_slice(payload);
        f
    }

    fn reply_cmds(replies: &[Vec<u8>]) -> Vec<String> {
        replies
            .iter()
            .filter(|r| r.len() > F_DATA + LAN_HDR && r[F_DATA] == TCP_DATA)
            .map(|r| cmd_name(&r[F_DATA + LAN_HDR..]))
            .collect()
    }

    #[test]
    fn make_command_matches_nfsuserver_length() {
        let b = make_command(
            "move",
            &["IDENT=1", "NAME=E.Main Lobby", "COUNT=0", "FLAGS=C"],
        );
        assert_eq!(
            b.len(),
            u32::from_be_bytes(b[8..12].try_into().unwrap()) as usize
        );
        assert!(b.starts_with(b"move"));
    }

    #[test]
    fn disconnect_releases_memberships_and_expires_abandoned_sockets() {
        let mut host = OnlineHost::new();
        let a = ConnKey {
            peer: 0x0a4d0002,
            sport: 40000,
            dport: PORT_LOBBY,
            cid: 1,
        };
        let b = ConnKey {
            peer: 0x0a4d0003,
            sport: 40001,
            dport: PORT_LOBBY,
            cid: 2,
        };
        for key in [a, b] {
            host.on_frame(&lan_tcp(
                key.peer,
                key.sport,
                key.dport,
                TCP_SYN,
                key.cid,
                &[],
            ));
            host.add_user_to_room(key, 1);
        }
        host.rooms[0].games.push(Game {
            id: 7,
            name: "Race".into(),
            params: String::new(),
            max: 4,
            min: 2,
            sysflags: 0,
            members: vec![a],
        });
        host.conns.get_mut(&a).unwrap().game_id = Some(7);
        let replies = host.disconnect_peer(a.peer);
        assert!(!host.conns.contains_key(&a));
        assert!(host.rooms[0].members == vec![b]);
        assert_eq!(host.rooms[0].count, 1);
        assert!(host.rooms[0].games.is_empty());
        assert!(reply_cmds(&replies).contains(&"+agm".into()));
        assert!(reply_cmds(&replies).contains(&"+pop".into()));
        assert!(replies
            .iter()
            .all(|r| u32::from_be_bytes(r[8..12].try_into().unwrap()) == b.peer));

        host.conns.get_mut(&b).unwrap().last_active = Instant::now() - CONNECTION_IDLE;
        let replies = host.keepalive_pings();
        assert!(host.conns.is_empty());
        assert!(host.rooms[0].members.is_empty());
        assert!(replies.iter().any(|r| r[F_DATA] == TCP_RST));
    }

    #[test]
    fn peer_socket_limit_and_repeated_syn_preserve_live_state() {
        let mut host = OnlineHost::new();
        let peer = 0x0a4d0002;
        for cid in 0..MAX_PEER_CONNECTIONS as u32 {
            let replies = host.on_frame(&lan_tcp(peer, 40000, PORT_LOBBY, TCP_SYN, cid, &[]));
            assert_eq!(replies[0][F_DATA], TCP_SYNACK);
        }
        let key = ConnKey {
            peer,
            sport: 40000,
            dport: PORT_LOBBY,
            cid: 0,
        };
        host.add_user_to_room(key, 1);
        let replies = host.on_frame(&lan_tcp(peer, 40000, PORT_LOBBY, TCP_SYN, 0, &[]));
        assert_eq!(replies[0][F_DATA], TCP_SYNACK);
        assert_eq!(host.conns[&key].room_id, Some(1));
        let replies = host.on_frame(&lan_tcp(peer, 40000, PORT_LOBBY, TCP_SYN, 99, &[]));
        assert_eq!(replies[0][F_DATA], TCP_RST);
        assert_eq!(host.conns.len(), MAX_PEER_CONNECTIONS);
        let replies = host.on_frame(&lan_tcp(
            peer,
            40000,
            PORT_LOBBY,
            TCP_DATA,
            0,
            &vec![0; MAX_COMMAND_BUFFER + 1],
        ));
        assert!(replies.iter().any(|r| r[F_DATA] == TCP_RST));
        assert!(!host.conns.contains_key(&key));
        assert!(host.rooms[0].members.is_empty());
    }

    #[test]
    fn move_into_room_emits_move_who_usr() {
        let mut host = OnlineHost::new();
        let peer = u32::from_be_bytes([10, 77, 0, 2]);
        let sport = 40000u16;
        let cid = 1u32;
        let syn = lan_tcp(peer, sport, PORT_LOBBY, TCP_SYN, cid, &[]);
        assert_eq!(host.on_frame(&syn).len(), 1);

        // Minimal persona/car so +who has content.
        let key_payload = make_command("pers", &["NAME=Racer2"]);
        let _ = host.on_frame(&lan_tcp(
            peer,
            sport,
            PORT_LOBBY,
            TCP_DATA,
            cid,
            &key_payload,
        ));

        let move_cmd = {
            let mut b = vec![0u8; 17];
            b[..4].copy_from_slice(b"move");
            b[8..12].copy_from_slice(&28u32.to_be_bytes());
            b.extend_from_slice(b"E.Main Lobby\0");
            // fix length
            let len = b.len() as u32;
            b[8..12].copy_from_slice(&len.to_be_bytes());
            b
        };
        let replies = host.on_frame(&lan_tcp(peer, sport, PORT_LOBBY, TCP_DATA, cid, &move_cmd));
        let names = reply_cmds(&replies);
        assert!(names.iter().any(|n| n.starts_with("move")), "{names:?}");
        assert!(names.iter().any(|n| n.starts_with("+who")), "{names:?}");
        assert!(names.iter().any(|n| n.starts_with("+usr")), "{names:?}");
        // No invented gcre (stock server waits for client).
        assert!(!names.iter().any(|n| n.starts_with("gcre")), "{names:?}");
    }

    #[test]
    fn gcre_speed_exe_kv_shape() {
        let mut host = OnlineHost::new();
        let peer = u32::from_be_bytes([10, 77, 0, 3]);
        let sport = 40001u16;
        let cid = 2u32;
        let _ = host.on_frame(&lan_tcp(peer, sport, PORT_LOBBY, TCP_SYN, cid, &[]));
        let _ = host.on_frame(&lan_tcp(
            peer,
            sport,
            PORT_LOBBY,
            TCP_DATA,
            cid,
            &make_command("pers", &["NAME=Host"]),
        ));
        let move_cmd = {
            let mut b = vec![0u8; 17];
            b[..4].copy_from_slice(b"move");
            b.extend_from_slice(b"E.Main Lobby\0");
            let len = b.len() as u32;
            b[8..12].copy_from_slice(&len.to_be_bytes());
            b
        };
        let _ = host.on_frame(&lan_tcp(peer, sport, PORT_LOBBY, TCP_DATA, cid, &move_cmd));

        // Speed.exe: NAME=%s ROOM=%s MAXSIZE=%d MINSIZE=2 SYSFLAGS=%d PARAMS=%s
        let gcre = make_command(
            "gcre",
            &[
                "NAME=TestRace",
                "ROOM=E.Main Lobby",
                "MAXSIZE=4",
                "MINSIZE=2",
                "SYSFLAGS=0",
                "PARAMS=",
            ],
        );
        let replies = host.on_frame(&lan_tcp(peer, sport, PORT_LOBBY, TCP_DATA, cid, &gcre));
        let names = reply_cmds(&replies);
        assert!(
            names
                .iter()
                .any(|n| n.starts_with("gcre") || n.starts_with("gjoi")),
            "{names:?}"
        );
        assert!(names.iter().any(|n| n.starts_with("+agm")), "{names:?}");
        let game = host
            .rooms
            .iter()
            .find(|r| r.name == "E.Main Lobby")
            .unwrap()
            .games
            .first()
            .unwrap();
        assert!(
            game.params.contains("TRACK%3d") && game.params.contains("%0a"),
            "empty PARAMS should get URL-encoded TRACK default, got {:?}",
            game.params
        );
    }

    #[test]
    fn mesg_preserves_challenge_flags_and_nested_text() {
        let mut host = OnlineHost::new();
        let a = u32::from_be_bytes([10, 77, 0, 10]);
        let b = u32::from_be_bytes([10, 77, 0, 11]);
        let _ = host.on_frame(&lan_tcp(a, 41000, PORT_LOBBY, TCP_SYN, 1, &[]));
        let _ = host.on_frame(&lan_tcp(b, 41001, PORT_LOBBY, TCP_SYN, 2, &[]));
        let _ = host.on_frame(&lan_tcp(
            a,
            41000,
            PORT_LOBBY,
            TCP_DATA,
            1,
            &make_command("pers", &["NAME=Alice"]),
        ));
        let _ = host.on_frame(&lan_tcp(
            b,
            41001,
            PORT_LOBBY,
            TCP_DATA,
            2,
            &make_command("pers", &["NAME=Bob"]),
        ));
        // Actual client format: PRIV=%s ATTR=%f TEXT=%s. GAME/PARAMS live
        // inside TEXT, escaped again by TagFieldSetString; not top-level KV.
        let invite = "GAME%3d7%0aPARAMS%3dTRACK%253d1003%250aDIR%253d0%250aLAPS%253d2%250aMYIP%253d172818443";
        for (attr, text, expected_flags, count) in [
            ("E0", invite, "E0P", 1),
            ("E1", "", "E1P", 1),
            ("E", "hello%3dworld", "EP", 2),
        ] {
            let mesg = make_command(
                "mesg",
                &["PRIV=Bob", &format!("ATTR={attr}"), &format!("TEXT={text}")],
            );
            let replies = host.on_frame(&lan_tcp(a, 41000, PORT_LOBBY, TCP_DATA, 1, &mesg));
            let msgs: Vec<_> = replies
                .iter()
                .filter(|r| r.len() > F_DATA + LAN_HDR && r[F_DATA] == TCP_DATA)
                .filter(|r| cmd_name(&r[F_DATA + LAN_HDR..]).starts_with("+msg"))
                .map(|r| {
                    let dst = u32::from_be_bytes(r[8..12].try_into().unwrap());
                    (dst, parse_kv_fields(&r[F_DATA + LAN_HDR..]))
                })
                .collect();
            assert_eq!(msgs.len(), count, "ATTR={attr}: {msgs:?}");
            assert_eq!(msgs[0].0, b, "{msgs:?}");
            assert_eq!(msgs[0].1.get("F").unwrap(), expected_flags);
            assert_eq!(msgs[0].1.get("T").unwrap(), text);
            assert_eq!(msgs[0].1.get("N").unwrap(), "Alice");
            if count == 2 {
                assert_eq!(msgs[1].0, a, "chat should echo to sender");
            }
        }
    }

    #[test]
    fn room_prefixes_abcdefg_h() {
        let host = OnlineHost::new();
        let names: Vec<_> = host.rooms.iter().map(|r| r.name.as_str()).collect();
        assert_eq!(
            names,
            [
                "A.Main Lobby",
                "B.Main Lobby",
                "C.Main Lobby",
                "D.Main Lobby",
                "E.Main Lobby",
                "F.Main Lobby",
                "G.Main Lobby",
                "H.Main Lobby"
            ]
        );
    }

    #[test]
    fn room_capacities_are_advertised_and_enforced_without_losing_previous_room() {
        for (global, capacity) in [(true, MAIN_ROOM_CAPACITY), (false, USER_ROOM_CAPACITY)] {
            let mut host = OnlineHost::new();
            let key = ConnKey {
                peer: 0x0a4d0002,
                sport: 40000,
                dport: PORT_LOBBY,
                cid: 1,
            };
            host.on_frame(&lan_tcp(
                key.peer,
                key.sport,
                key.dport,
                TCP_SYN,
                key.cid,
                &[],
            ));
            host.add_user_to_room(key, 2);
            host.rooms[1].games.push(Game {
                id: 7,
                name: "Race".into(),
                params: String::new(),
                max: 4,
                min: 2,
                sysflags: 0,
                members: vec![key],
            });
            host.conns.get_mut(&key).unwrap().game_id = Some(7);
            host.rooms[0].global = global;
            let fill = capacity - 1;
            host.rooms[0].members = (0..fill)
                .map(|n| ConnKey {
                    peer: 0x0a4d0100 + n,
                    ..key
                })
                .collect();
            host.rooms[0].count = fill;

            let listing = host.room_list_msgs(key.peer, key.sport, key.dport, key.cid);
            assert_eq!(
                parse_kv_fields(&listing[0][F_DATA + LAN_HDR..]).get("L"),
                Some(&capacity.to_string())
            );

            let last = ConnKey {
                peer: 0x0a4d0700,
                ..key
            };
            host.on_frame(&lan_tcp(
                last.peer,
                last.sport,
                last.dport,
                TCP_SYN,
                last.cid,
                &[],
            ));
            host.add_user_to_room(last, 1);
            assert_eq!(host.rooms[0].count, capacity);

            let replies = host.add_user_to_room(key, 1);
            assert_eq!(reply_cmds(&replies), vec!["movefull"]);
            assert_eq!(host.conns[&key].room_id, Some(2));
            assert_eq!(host.conns[&key].game_id, Some(7));
            assert!(host.rooms[1].games[0].members == vec![key]);
            assert_eq!(host.rooms[0].count, capacity);
        }

        let mut host = OnlineHost::new();
        let key = ConnKey {
            peer: 0x0a4d0002,
            sport: 40000,
            dport: PORT_LOBBY,
            cid: 1,
        };
        host.on_frame(&lan_tcp(
            key.peer,
            key.sport,
            key.dport,
            TCP_SYN,
            key.cid,
            &[],
        ));
        let mut request = vec![0u8; 17];
        request.extend_from_slice(b"E.Crew\0");
        let replies = host.handle_room(key, &request);
        for command in ["room", "+rom"] {
            let reply = replies
                .iter()
                .find(|r| cmd_name(&r[F_DATA + LAN_HDR..]) == command)
                .unwrap();
            let field = if command == "room" { "LIMIT" } else { "L" };
            assert_eq!(
                parse_kv_fields(&reply[F_DATA + LAN_HDR..]).get(field),
                Some(&USER_ROOM_CAPACITY.to_string())
            );
        }
    }

    #[test]
    fn snap_returns_ack_and_snp_rows() {
        let mut host = OnlineHost::new();
        let peer = u32::from_be_bytes([10, 77, 0, 4]);
        let sport = 40002u16;
        let cid = 3u32;
        let _ = host.on_frame(&lan_tcp(peer, sport, PORT_LOBBY, TCP_SYN, cid, &[]));
        let snap = make_command("snap", &["INDEX=1", "CHAN=0", "START=0", "RANGE=100"]);
        let replies = host.on_frame(&lan_tcp(peer, sport, PORT_LOBBY, TCP_DATA, cid, &snap));
        let names = reply_cmds(&replies);
        assert!(names.iter().any(|n| n.starts_with("snap")), "{names:?}");
        assert!(
            names.iter().filter(|n| n.starts_with("+snp")).count() >= 1,
            "{names:?}"
        );
    }

    #[test]
    fn gdel_removes_challenge() {
        let mut host = OnlineHost::new();
        let peer = u32::from_be_bytes([10, 77, 0, 5]);
        let sport = 40003u16;
        let cid = 4u32;
        let _ = host.on_frame(&lan_tcp(peer, sport, PORT_LOBBY, TCP_SYN, cid, &[]));
        let _ = host.on_frame(&lan_tcp(
            peer,
            sport,
            PORT_LOBBY,
            TCP_DATA,
            cid,
            &make_command("pers", &["NAME=Host"]),
        ));
        let mut move_cmd = vec![0u8; 17];
        move_cmd[..4].copy_from_slice(b"move");
        move_cmd.extend_from_slice(b"E.Main Lobby\0");
        let len = move_cmd.len() as u32;
        move_cmd[8..12].copy_from_slice(&len.to_be_bytes());
        let _ = host.on_frame(&lan_tcp(peer, sport, PORT_LOBBY, TCP_DATA, cid, &move_cmd));
        let gcre = make_command(
            "gcre",
            &[
                "NAME=DelMe",
                "ROOM=E.Main Lobby",
                "MAXSIZE=4",
                "MINSIZE=2",
                "SYSFLAGS=0",
                "PARAMS=",
            ],
        );
        let _ = host.on_frame(&lan_tcp(peer, sport, PORT_LOBBY, TCP_DATA, cid, &gcre));
        assert_eq!(
            host.rooms
                .iter()
                .find(|r| r.name == "E.Main Lobby")
                .unwrap()
                .games
                .len(),
            1
        );
        let mut gdel = vec![0u8; 17];
        gdel[..4].copy_from_slice(b"gdel");
        gdel.extend_from_slice(b"DelMe\0");
        let len = gdel.len() as u32;
        gdel[8..12].copy_from_slice(&len.to_be_bytes());
        let replies = host.on_frame(&lan_tcp(peer, sport, PORT_LOBBY, TCP_DATA, cid, &gdel));
        let names = reply_cmds(&replies);
        assert!(names.iter().any(|n| n.starts_with("gdel")), "{names:?}");
        assert!(host
            .rooms
            .iter()
            .find(|r| r.name == "E.Main Lobby")
            .unwrap()
            .games
            .is_empty());
    }
}
