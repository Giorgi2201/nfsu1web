"""Patch the pinned browser input adapter to consume local keyboard aliases."""
from __future__ import annotations


def _exact(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"keyboard overlay expected one occurrence, found {count}: {old[:80]!r}")
    return source.replace(old, new, 1)


def keyboard_input(source: str) -> str:
    source = _exact(source, "import { PadPoller } from './gamepad';",
                    "import { translateKeyboardEvent } from '../app/keyboard';\nimport { PadPoller } from './gamepad';")
    source = _exact(source, "  // ---- the event ring -------------------------------------------------------",
                    """  // Track physical sources independently: WASD and arrows can hold the same game key.
  const heldSources = new Map<string, { code: string; vk: number }>();
  const heldTargets = new Map<number, number>();

  // ---- the event ring -------------------------------------------------------""")
    source = _exact(source,
                    "  function push(type: number, dik = 0, vk = 0, flags = 0, chars: number[] = [], a = 0, b = 0) {\n",
                    """  function push(type: number, dik = 0, vk = 0, flags = 0, chars: number[] = [], a = 0, b = 0) {
    if (type === IEV_RELEASE_ALL || (type === IEV_FOCUS && !a)) {
      heldSources.clear(); heldTargets.clear();
    }
""")
    source = _exact(source,
                    "    if (detached || ignored(e) || e.isComposing || e.keyCode === 229) return;",
                    """    if (detached || e.isComposing || e.keyCode === 229) return;
    if (ignored(e)) {
      if (heldSources.size) push(IEV_RELEASE_ALL, 0, 0, 0, [], 0, IREASON_PAGE);
      return;
    }""")
    source = _exact(source,
                    """    const k = CODES[e.code];
    if (!k) return;
    if (!pass.has(e.code)) e.preventDefault();
    if (mac && e.code === 'CapsLock') { push(IEV_KEY_TAP, k.dik, k.vk, flagsOf(e)); return; }
    const { chars, dead, sys } = charsOf(e.code, e);
    push(IEV_KEY_DOWN, k.dik, vkOf(e.code, e, k.vk), flagsOf(e) | (e.repeat ? IKF_REPEAT : 0) | (dead ? IKF_DEAD : 0), chars, 0, sys);""",
                    """    const held = heldSources.get(e.code);
    const code = held?.code ?? translateKeyboardEvent(e) ?? e.code;
    const k = CODES[code];
    if (!k) return;
    if (!pass.has(e.code)) e.preventDefault();
    if (mac && e.code === 'CapsLock') { push(IEV_KEY_TAP, k.dik, k.vk, flagsOf(e)); return; }
    const remapped = code !== e.code;
    const vk = held?.vk ?? (remapped ? k.vk : vkOf(code, e, k.vk));
    if (!held) {
      const count = heldTargets.get(k.dik) ?? 0;
      heldSources.set(e.code, { code, vk });
      heldTargets.set(k.dik, count + 1);
      if (count) return; // another physical key already holds this destination
    }
    const { chars, dead, sys } = remapped ? { chars: [], dead: false, sys: 0 } : charsOf(code, e);
    push(IEV_KEY_DOWN, k.dik, vk, flagsOf(e) | (e.repeat ? IKF_REPEAT : 0) | (dead ? IKF_DEAD : 0), chars, 0, sys);""")
    source = _exact(source,
                    """    const k = CODES[e.code];
    if (!k) return;
    if (!pass.has(e.code) && !ignored(e)) e.preventDefault();   // also keeps Alt from opening a menu bar
    if (mac && e.code === 'CapsLock') { push(IEV_KEY_TAP, k.dik, k.vk, flagsOf(e)); return; }
    push(IEV_KEY_UP, k.dik, k.vk, flagsOf(e));""",
                    """    if (!pass.has(e.code) && !ignored(e)) e.preventDefault();
    if (mac && e.code === 'CapsLock') {
      const k = CODES[e.code];
      if (k) push(IEV_KEY_TAP, k.dik, k.vk, flagsOf(e));
      return;
    }
    const held = heldSources.get(e.code);
    if (!held) return; // a capture or a release-all may have consumed its keydown
    heldSources.delete(e.code);
    const k = CODES[held.code];
    const count = (heldTargets.get(k.dik) ?? 1) - 1;
    if (count) { heldTargets.set(k.dik, count); return; }
    heldTargets.delete(k.dik);
    push(IEV_KEY_UP, k.dik, held.vk, flagsOf(e));""")
    source = _exact(source,
                    "  kbTarget.addEventListener('keydown', onKeyDown as EventListener, { capture: true });",
                    """  const onKeyboardChange = () => api.releaseAll();
  const onUiFocus = (e: Event) => { if (ignored(e) && heldSources.size) api.releaseAll(); };
  addEventListener('nfsu1-keyboard-change', onKeyboardChange);
  document.addEventListener('focusin', onUiFocus, { capture: true });
  kbTarget.addEventListener('keydown', onKeyDown as EventListener, { capture: true });""")
    source = _exact(source,
                    "      kbTarget.removeEventListener('keydown', onKeyDown as EventListener, { capture: true });",
                    """      removeEventListener('nfsu1-keyboard-change', onKeyboardChange);
      document.removeEventListener('focusin', onUiFocus, { capture: true });
      kbTarget.removeEventListener('keydown', onKeyDown as EventListener, { capture: true });""")
    return source
