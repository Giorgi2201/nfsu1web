#!/usr/bin/env python3
"""Apply or revert the reversible PC NFSU1 browser bring-up overlay.

The overlay is anchored to th0mk/nfsu2-web at 31da468582c3de14fd6f4233831f62816e2df83d.
Upstream excerpts are reused under MIT; see patches/nfsu2-web.LICENSE.
It changes only hand-written web app files. The game data, generated code, and
WebGPU/audio/input host ABI remain supplied by the root integration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "31da468582c3de14fd6f4233831f62816e2df83d"
FILES = {
    "web/index.html": "dcd0d50b384ec6af61e836e8406514f9ee3cb735",
    "web/src/app/game.ts": "a15310956e31c313fd61e9454f408421fc353729",
    "web/src/app/settings-ui.ts": "e5d113afdb1e54abfd6851044a922c9d14d464b7",
    "web/src/app/settings.ts": "7a279d9661886e97619c74ae7e2e60f13233a603",
    "web/src/app/shell.ts": "d76dc20bc5b9e2a8a7a8a8397dac28df36031419",
    "web/src/host/datacache.ts": "0996277c86f91168cd3ff0c5cb1f22e39ae3a177",
    "web/src/sw.ts": "406d25673604f4f03cc5b41a112c37f68063f689",
}
STATE_DIR = ".nfsu1-browser-profile"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def exact(source: str, old: str, new: str, *, count: int = 1) -> str:
    got = source.count(old)
    if got != count:
        raise ValueError(f"expected {count} anchored occurrence(s), found {got}: {old[:70]!r}")
    return source.replace(old, new, count)


def transform(path: str, source: str) -> str:
    if path == "web/src/app/game.ts":
        return exact(source, "args: ['nfsu2', '/data/SPEED2.EXE']", "args: ['nfsu1', '/data/Speed.exe']")

    if path == "web/src/app/settings.ts":
        source = exact(source, "NFSU2_FNG_LOG: '1', NFSU2_STATUS_EVERY: '3600', NFSU2_AUDIO_STATUS: '0',",
                       "NFSU2_FNG_LOG: '0', NFSU2_STATUS_EVERY: '0', NFSU2_AUDIO_STATUS: '0',")
        return source

    if path == "web/src/app/settings-ui.ts":
        start = source.index("const GROUPS: Group[] = [")
        end = source.index("\n];", start) + 3
        replacement = '''const GROUPS: Group[] = [
  { title: 'Browser', items: [
    { key: 'fullscreen', label: 'Full screen on Play', help: 'Open the game canvas full screen when the browser allows it.', c: { t: 'switch' } },
    { key: 'audio_latency', label: 'Audio latency', help: 'Choose the browser audio output buffer.', c: { t: 'seg', opts: [['interactive', 'Low'], ['balanced', 'Balanced'], ['playback', 'Robust']] } },
  ] },
  { title: 'Input device', items: [
    { key: 'gamepad', label: 'Controller input', help: 'Choose whether the browser exposes a connected game controller to the runtime.', c: { t: 'seg', opts: [['on', 'On'], ['hotplug', 'While connected'], ['off', 'Off']] } },
    { key: 'gamepad_deadzone', label: 'Stick dead zone', help: 'Fraction of full stick travel ignored by the browser input adapter.', c: { t: 'num', min: 0, max: 0.9, step: 0.01 } },
    { key: 'gamepad_trigger_deadzone', label: 'Trigger dead zone', help: 'Fraction of full trigger travel ignored by the browser input adapter.', c: { t: 'num', min: 0, max: 0.9, step: 0.01 } },
  ] },
];'''
        return source[:start] + replacement + source[end:]

    if path == "web/src/host/datacache.ts":
        return exact(source, "export const CACHE_DIR = 'cache';", "export const CACHE_DIR = 'cache-nfsu1';")

    if path == "web/src/sw.ts":
        source = exact(source, "const CACHE = 'nfsu2-offline-2';", "const CACHE = 'nfsu1-offline-1';")
        return exact(source, "k.startsWith('nfsu2-offline-')", "k.startsWith('nfsu1-offline-')")

    if path == "web/src/app/shell.ts":
        source = exact(source, "let SAVE = 'save';", "let SAVE = 'save-nfsu1';")
        source = exact(source, "const ASK_ROAM = true;", "const ASK_ROAM = false;")
        source = exact(source, "  const r = resolved(host);", """  const r = resolved(host);
  // Preserve shared host options; filter unsupported game variables before startup.
  Object.assign(r.env, {
    NFSU2_AUTOSAVE: '0', NFSU2_NET: 'off', NFSU2_ONLINE: '0', NFSU2_ROAM: '0',
    NFSU2_SEED_REGISTRY: '0', NFSU2_FPS_COUNTER: 'off', NFSU2_PAD_FE_KEYS: '0',
    NFSU2_FNG_LOG: '0', NFSU2_STATUS_EVERY: '0', NFSU2_AUDIO_STATUS: '0',
  });""")
        source = exact(source,
                       "setPhase('ready', 'Ready', offline ? 'Offline: the game runs from this PC, without free roam or Online. Press Play or Enter to start.'\n    : 'Press Play or Enter to start.');",
                       "setPhase('ready', 'Ready', offline ? 'Offline. Press Start experiment or Enter.'\n    : 'Press Start experiment or Enter.');")
        source = exact(source, "setPhase('starting', 'Starting', full ? 'Going full screen and starting the game.' : 'Starting the game.');",
                       "setPhase('starting', 'Starting experiment', full ? 'Going full screen and starting the experimental runtime.' : 'Starting the experimental runtime.');")
        source = exact(source, "setPhase('playing', 'Playing', '');", "setPhase('playing', 'Runtime experiment running', '');")
        source = exact(source, "=== NFSU2 web,", "=== PC NFSU1 experimental browser bring-up,")
        source = exact(source, "downloadBlob(log.text(), `nfsu2-${stamp()}.log`, 'text/plain');",
                       "downloadBlob(log.text(), `nfsu1-${stamp()}.log`, 'text/plain');")
        start = source.index("  // the game's Save option at Autosave, once per profile")
        end = source.index("  if (q.get('script')) {", start)
        source = source[:start] + "  // NFSU1 overlay: never rewrite profile bytes using the NFSU2 save layout.\n" + source[end:]
        source = exact(source,
                       "  if (autosaved.length) toast(`Autosave is now on for ${autosaved.join(', ')}: the game saves by itself (Options, Gameplay, Save). ${hint}`, 9000);\n  else toast(hint, 6000);",
                       "  toast(hint, 6000);")
        source = exact(source, "  const net = !/^(off|0|none)$/i.test(r.env.NFSU2_NET?.trim() ?? '');\n  const netName = net ? (r.env.NFSU2_ROAM_NAME?.trim() || 'Player') : null;",
                       "  const netName = null; // no NFSU2 LAN, Online, or free-roam integration in this profile.")
        source = exact(source,
                       "    HOME: '/save', NFSU2_DATA: '/data', NFSU2_SAVEDIR: '/save', NFSU2_REGFILE: '/save/registry.txt',",
                       "    HOME: '/save', NFSU2_DATA: '/data', NFSU2_SAVEDIR: '/save', NFSU2_REGFILE: '/save/registry.txt',\n    NFSU1_SAVEDIR: '/save/nfsu1', NFSU1_READONLY_DATA: '1',")
        source = exact(source, "  hudWide = !/^(43|4:3)$/i.test(r.env.NFSU2_HUD?.trim() ?? '');",
                       "  hudWide = true; // no NFSU2 HUD layout option is applied to the NFSU1 experiment.")
        source = exact(source,
                       "      module: loaded!.module, info: loaded!.info, saveDir: SAVE, env: r.env, canvas, stage, audio, displayHz, netName, notice, netBack, onSaved,",
                       """      module: loaded!.module, info: loaded!.info, saveDir: SAVE, env: browserEnv(r.env), canvas, stage, audio, displayHz, netName, notice, netBack, onSaved,""")
        source = exact(source, "function logLine(s: string) { log.add(s); }",
                       """const BROWSER_ENV = new Set([
  'HOME', 'NFSU2_DATA', 'NFSU2_SAVEDIR', 'NFSU2_REGFILE', 'NFSU2_WIDTH', 'NFSU2_HEIGHT',
  'NFSU2_DISPLAY_HZ', 'NFSU2_RENDERER', 'NFSU2_READONLY_DATA', 'NFSU1_SAVEDIR', 'NFSU1_READONLY_DATA',
  'GPUVS', 'FIXMAT', 'FIXMAT_MODE', 'ALARM', 'NOMOVIES', 'SNDSYNC', 'NFSFULL', 'NFSRES', 'NFSMAXPIX',
  'NFSU2_PAD', 'NFSU2_PAD_DEADZONE', 'NFSU2_PAD_TRIGGER_DEADZONE', 'NFSU2_PAD_TRIGGER_CLICK', 'NFSU2_FF',
  'NFSU2_AUDIO_LATENCY', 'NFSU2_TZ', 'NFSU2_TZ_NAME',
  'NFSU1_DIAGNOSTICS', 'NFSU1_DIAGNOSTIC_WORDS', 'COMTRACE', 'TRACE_MAX', 'FILELIST', 'PRESENTBT', 'BT',
  'NFSU2_AUTOSAVE', 'NFSU2_NET', 'NFSU2_ONLINE', 'NFSU2_ROAM', 'NFSU2_SEED_REGISTRY', 'NFSU2_FPS_COUNTER', 'NFSU2_PAD_FE_KEYS',
]);
/** Pass only host contracts and explicitly supported bring-up diagnostics to the process. */
function browserEnv(input: Record<string, string>): Record<string, string> {
  const out = Object.fromEntries(Object.entries(input).filter(([key]) => BROWSER_ENV.has(key)));
  Object.assign(out, { NFSU2_AUTOSAVE: '0', NFSU2_NET: 'off', NFSU2_ONLINE: '0', NFSU2_ROAM: '0',
    NFSU2_SEED_REGISTRY: '0', NFSU2_FPS_COUNTER: 'off', NFSU2_PAD_FE_KEYS: '0',
    NFSU1_SAVEDIR: '/save/nfsu1', NFSU1_READONLY_DATA: '1' });
  return out;
}

function logLine(s: string) { log.add(s); }""")
        source = exact(source, "  m.querySelector<HTMLButtonElement>('[data-act=\"fps\"]')!.textContent = `Frame-rate counter: ${fps.mode}`;\n", "")
        source = exact(source, "    case 'fps': fps.cycle(); m.querySelector<HTMLButtonElement>('[data-act=\"fps\"]')!.textContent = `Frame-rate counter: ${fps.mode}`; break;\n", "")
        source = exact(source, "  // F8 / F9 belong to the page while the game runs (the game binds neither,\n  // Chrome reserves neither); caught first, so the game never sees them.",
                       "  // F9 opens the page menu while the runtime runs.")
        old_quit = """    case 'quit': {
      m.close();
      const s = session;
      if (!s) break;
      const stage = quitStage(s);
      if (stage === 0) {
        if (s.requestQuit()) { quitAt = { s, t: performance.now(), forced: false }; toast('Quitting: the game saves and closes.', 5000); break; }
      } else if (stage === 1) {
        // the game's own second-request rule: open save files are finished, then it exits
        if (await confirmBox('Close the game now?', 'The game has not closed yet (a loading screen ignores Quit). Closing now finishes any save in progress first.', 'Close now', true, 'quit') && session === s) {
          if (s.requestQuit()) { quitAt = { s, t: performance.now(), forced: true }; toast('Closing the game.', 4000); break; }
        } else break;
      }
      // the game cannot be asked (any more), or it did not close when asked twice
      if (await confirmBox('Stop the game now?', s.canQuit()
          ? 'The game did not close when asked. Stopping it ends it at once: progress since it last saved is lost.'
          : 'The game cannot be asked to quit, so it is stopped at once. Progress since it last saved is lost.', 'Stop the game', true, 'quit') && session === s) s.terminate();
      break;
    }
"""
        new_quit = """    case 'quit': {
      m.close();
      const s = session;
      if (!s) break;
      if (await confirmBox('Stop experiment?', 'The experimental runtime will be stopped immediately.', 'Stop experiment', true, 'quit') && session === s) s.terminate();
      break;
    }
"""
        source = exact(source, old_quit, new_quit)
        source = exact(source, "function quitLabel(): string {\n  if (!session) return 'Quit game';\n  return ['Quit game', 'Close the game now', 'Stop the game'][quitStage(session)];\n}",
                       "function quitLabel(): string { return 'Stop experiment'; }")
        source = exact(source, "    if (session && (e.code === 'F8' || e.code === 'F9')) {\n      e.preventDefault(); e.stopImmediatePropagation();\n      if (e.repeat) return;\n      if (e.code === 'F8') toast(`Frame-rate counter: ${fps.cycle()}`, 1500); else openMenu();",
                       "    if (session && e.code === 'F9') {\n      e.preventDefault(); e.stopImmediatePropagation();\n      if (e.repeat) return;\n      openMenu();")
        source = exact(source, "  instance = claimInstance(`nfsu2-saves:${SAVE}`);", "  instance = claimInstance(`nfsu1-saves:${SAVE}`);")
        source = exact(source, "  players = watchPlayers(line => settings.setStatus(line), () => !session && !starting, setReach);",
                       "  players = null; // NFSU2-only player directory and online controls are disabled.")
        source = exact(source, "let saved: { name: string; at: number; count: number } | null = null;",
                       "let saved: { at: number; count: number } | null = null;")
        old_exit = """    // what is kept: the game's last profile save, never a claim it did not make
    const sv = saved;
    setPhase('exited', code === 0 ? 'See you' : 'Stopped', !sv ? base : code === 0 ? `${base} Progress saved in this browser at ${when(sv.at)} (${sv.name}).`
      : `${base} Your progress up to the last save, at ${when(sv.at)} (${sv.name}), is kept.`);
    if (!sv) void newestProfile().then(p => {
      const sub = $('#status-sub');
      if (phase === 'exited' && !session && sub.textContent === base)
        sub.textContent = `${base} ${p ? `Nothing was saved during this game; the last save is from ${when(p.mtime)} (${p.name}).` : 'No profile is saved in this browser yet.'}`;
    });"""
        new_exit = """    const sv = saved;
    setPhase('exited', code === 0 ? 'Experiment ended' : 'Stopped', !sv
      ? `${base} No file writes were reported.`
      : `${base} ${sv.count} file write(s) were reported during this experiment at ${when(sv.at)}.`);"""
        source = exact(source, old_exit, new_exit)
        source = exact(source,
                       "    const base = code === 0 ? `The game closed normally after ${mins}.` : code === -1 ? `The game was stopped after ${mins}.`\n      : `The game stopped with error code ${code} after ${mins}.`;",
                       "    const base = code === 0 ? `The runtime exited normally after ${mins}.` : code === -1 ? `The runtime was stopped after ${mins}.`\n      : `The runtime stopped with error code ${code} after ${mins}.`;")
        old_saved = """/** the game finished writing a file of the save folder: a profile is the player's progress */
function onSaved(path: string) {
  const p = path.split('/');
  if (p.length !== 3 || p[0] !== PROFILES_DIR || p[2].toLowerCase() !== p[1].toLowerCase()) return;
  saved = { name: p[1], at: Date.now(), count: (saved?.count ?? 0) + 1 };
  log.add(`[app] the game saved profile ${p[1]} (${saved.count} this game)`);
  if (session) toast(`Progress saved (${p[1]}).`, 2500);
  if ($<HTMLDialogElement>('#menu').open) $('#menu-save').textContent = `Last saved at ${when(saved.at)} (${saved.name}).`;
}
"""
        new_saved = """/** The host reported a closed file in the isolated save mount; its format is unknown. */
function onSaved(path: string) {
  saved = { at: Date.now(), count: (saved?.count ?? 0) + 1 };
  log.add(`[app] a file was written in isolated browser storage (${saved.count} reported this experiment)`);
  if (session) toast('A file was written to isolated browser storage.', 3000);
  if ($<HTMLDialogElement>('#menu').open) $('#menu-save').textContent = `File writes reported: ${saved.count}.`;
}
"""
        source = exact(source, old_saved, new_saved)
        old_menu = """  const line = $('#menu-save');
  if (saved) line.textContent = `Last saved at ${when(saved.at)} (${saved.name}).`;
  else {
    line.textContent = 'Nothing saved during this game yet.';
    void newestProfile().then(p => {
      if (!saved && m.open) line.textContent = p ? `Nothing saved during this game yet. Last save: ${when(p.mtime)} (${p.name}).` : 'No profile is saved in this browser yet.';
    });
  }
"""
        new_menu = """  const line = $('#menu-save');
  line.textContent = saved ? `File writes reported: ${saved.count}.` : 'No file writes reported during this experiment.';
"""
        source = exact(source, old_menu, new_menu)
        return source

    if path == "web/index.html":
        source = exact(source, "<title>Underground 2 Revived</title>", "<title>PC NFS Underground 1 Experimental Bring-up</title>")
        source = exact(source, "Play Need for Speed: Underground 2 (2004) in Chrome and Firefox with WebGPU graphics, Web Audio, up to 120 fps widescreen, controller support, free roam and Online races with friends.",
                       "Experimental PC Need for Speed: Underground 1 browser build. Compatibility remains under testing.", count=3)
        source = exact(source, "Need for Speed Underground 2, NFSU2, Underground 2 browser, play NFSU2 online, WebAssembly, WebGPU, free roam multiplayer, racing game",
                       "Need for Speed Underground 1, NFSU1, browser runtime integration research, WebAssembly")
        source = exact(source, 'content="Underground 2 Revived"', 'content="PC NFS Underground 1 Experimental Bring-up"', count=4)
        source = exact(source, '"@type": ["VideoGame", "WebApplication"]', '"@type": "WebApplication"')
        source = exact(source, '"name": "Underground 2 Revived"', '"name": "PC NFS Underground 1 Experimental Bring-up"')
        source = exact(source, '"alternateName": ["Need for Speed: Underground 2 in the browser", "NFSU2", "Need for Speed Underground 2"]',
                       '"alternateName": ["Need for Speed: Underground 1 browser-runtime research", "NFSU1"]')
        source = exact(source, '"description": "Need for Speed: Underground 2 (2004), recompiled to WebAssembly to run in Chrome and Firefox with WebGPU graphics, Web Audio, up to 120 fps widescreen, Xbox and PlayStation controller support, free roam and Online multiplayer."',
                       '"description": "Experimental PC NFS Underground 1 browser build. Compatibility remains under testing."')
        source = exact(source, '"applicationCategory": "GameApplication",\n  "genre": "Racing",\n  "gamePlatform": "Web browser",\n  "operatingSystem": "Windows, macOS",\n  "playMode": ["SinglePlayer", "MultiPlayer", "CoOp"]',
                       '"applicationCategory": "DeveloperApplication"')
        source = exact(source, '<h1>Underground 2 Revived</h1>', '<h1>PC NFS Underground 1 Experimental Bring-up</h1>')
        source = exact(source, '<section class="panel hero" aria-label="Play">',
                       '<section class="panel hero" aria-label="Experimental PC NFS Underground 1 bring-up">\n      <p class="msg warn">Experimental PC NFS Underground 1 browser build. Full game compatibility is still under testing.</p>')
        source = exact(source,
                       '<p class="msg" id="report" hidden>Help get it fixed: download the log and post it in <a href="https://discord.gg/SSHm5g43gh"target="_blank" rel="noopener noreferrer">#bug-reports on our Discord</a>, with what you were doing when it happened.</p>',
                       '<p class="msg" id="report" hidden>Download the log and share it with the test results.</p>')
        community = re.compile(r'        <a class="btn" href="https://discord\.gg/25zXmQ2Ua9"[^>]*>.*?</a>\n', re.S)
        source, count = community.subn('', source)
        if count != 1:
            raise ValueError(f"expected one upstream community CTA, found {count}")
        source = exact(source, '>Play <kbd>Enter</kbd>', '>Start experiment <kbd>Enter</kbd>')
        source = exact(source, '<section class="panel" id="controls" aria-labelledby="controls-title">',
                       '<section class="panel" id="controls" aria-labelledby="controls-title" hidden>')
        controls_start = source.index('      <div id="keys">')
        controls_end_marker = '      </div>\n    </section>\n\n    <section class="panel" id="changes"'
        controls_end = source.index(controls_end_marker, controls_start)
        source = (source[:controls_start] +
                  '      <div id="keys"><p>Keyboard and controller mappings are undocumented for this experimental PC NFSU1 bring-up.</p>\n' +
                  source[controls_end:])
        source = exact(source, '<section class="panel" id="changes" aria-labelledby="changes-title">',
                       '<section class="panel" id="changes" aria-labelledby="changes-title" hidden>')
        source = exact(source, '<section class="panel" id="saves" aria-labelledby="saves-title">',
                       '<section class="panel" id="saves" aria-labelledby="saves-title" hidden>')
        source = exact(source, '<section class="panel" id="online" aria-labelledby="online-title">',
                       '<section class="panel" id="online" aria-labelledby="online-title" hidden>')
        source = exact(source, '<details class="raw" id="settings-raw">',
                       '<details class="raw" id="settings-raw" hidden>')
        source = exact(source, '    <button type="button" class="btn" data-act="fps">Frame-rate counter: off</button>\n', '')
        return source

    raise ValueError(f"unrecognized browser overlay path: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True, help="pinned nfsu2-web checkout root")
    parser.add_argument("--revert", action="store_true", help="restore files changed by this overlay")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    state_dir = upstream / STATE_DIR
    state_path = state_dir / "state.json"

    if args.revert:
        state = json.loads(state_path.read_text())
        for name, info in state["files"].items():
            target = upstream / name
            if hashlib.sha256(target.read_bytes()).hexdigest() != info["applied_sha256"]:
                raise ValueError(f"refusing to discard later edits in {name}")
        for name, info in state["files"].items():
            (upstream / name).write_bytes((state_dir / name).read_bytes())
        state_path.unlink()
        print(f"Restored {len(state['files'])} browser files from {STATE_DIR}.")
        return

    if state_path.exists():
        state = json.loads(state_path.read_text())
        for name, info in state["files"].items():
            if hashlib.sha256((upstream / name).read_bytes()).hexdigest() != info["applied_sha256"]:
                raise ValueError(f"overlay file has later edits: {name}")
        print(f"PC NFSU1 browser overlay already applied and unchanged ({len(state['files'])} files).")
        return

    outputs: dict[str, bytes] = {}
    originals: dict[str, bytes] = {}
    for name, expected in FILES.items():
        target = upstream / name
        data = target.read_bytes()
        actual = git_blob(data)
        if actual != expected:
            raise ValueError(f"{name} is not the pinned upstream blob: expected {expected}, found {actual}")
        originals[name] = data
        outputs[name] = transform(name, data.decode("utf-8")).encode("utf-8")

    state_dir.mkdir(parents=True, exist_ok=True)
    state = {"upstream_commit": COMMIT, "files": {}}
    for name, data in originals.items():
        (state_dir / name).parent.mkdir(parents=True, exist_ok=True)
        (state_dir / name).write_bytes(data)
        target = upstream / name
        target.write_bytes(outputs[name])
        state["files"][name] = {"original_sha256": hashlib.sha256(data).hexdigest(),
                                "applied_sha256": hashlib.sha256(outputs[name]).hexdigest()}
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"Applied PC NFSU1 browser overlay to {len(outputs)} pinned files under {upstream}.")
    for name in outputs:
        print(f"  {name}")
    print(f"Revert with: python3 tools/apply_browser_profile.py --upstream {upstream} --revert")


if __name__ == "__main__":
    main()
