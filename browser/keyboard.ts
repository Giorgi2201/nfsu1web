// Browser key aliases. The game's own Controls menu remains the source of action bindings.
const STORAGE_KEY = 'nfsu1-keyboard-v1';
const TARGETS = [
  { code: 'ArrowUp', action: 'Throttle' },
  { code: 'ArrowDown', action: 'Brake / reverse' },
  { code: 'ArrowLeft', action: 'Steer left' },
  { code: 'ArrowRight', action: 'Steer right' },
  { code: 'Space', action: 'Handbrake' },
  { code: 'AltLeft', action: 'Nitrous' },
  { code: 'ShiftLeft', action: 'Shift up (manual)' },
  { code: 'ControlLeft', action: 'Shift down (manual)' },
  { code: 'KeyC', action: 'Change camera' },
  { code: 'KeyB', action: 'Look back' },
  { code: 'KeyR', action: 'Reset car' },
] as const;
type Target = typeof TARGETS[number]['code'];
const targetCodes = TARGETS.map(({ code }) => code) as Target[];
type Bindings = Partial<Record<Target, string>>;
const RESERVED = new Set(['Escape', 'Enter', 'Tab', 'F9', 'F10', 'F11', 'F12', 'MetaLeft', 'MetaRight', 'OSLeft', 'OSRight', 'CapsLock']);
const validCode = (code: unknown): code is string => typeof code === 'string' && !RESERVED.has(code) && /^(Key[A-Z]|Digit[0-9]|Arrow(Up|Down|Left|Right)|Space|Shift(Left|Right)|Control(Left|Right)|Alt(Left|Right)|Backspace|Home|End|Page(Up|Down)|Insert|Delete|Minus|Equal|Bracket(Left|Right)|Backslash|Semicolon|Quote|Backquote|Comma|Period|Slash|Numpad([0-9]|Add|Subtract|Multiply|Divide|Decimal|Enter)|F[1-8]|F10)$/.test(code);

function readBindings(): Bindings {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}');
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const result: Bindings = {}, used = new Set<string>();
    for (const target of targetCodes) {
      const source = (parsed as Record<string, unknown>)[target];
      if (validCode(source) && source !== target && !(source.startsWith('Alt') && target !== 'AltLeft') && !used.has(source)) {
        result[target] = source;
        used.add(source);
      }
    }
    // Reject sources that would override another row still showing its original key.
    for (const target of targetCodes) {
      const source = result[target];
      if (source && targetCodes.includes(source as Target) && !result[source as Target]) delete result[target];
    }
    return result;
  } catch { return {}; }
}

let bindings = readBindings();
let aliasesEnabled = true;

/** Temporarily restore original keys for in-game text entry. */
export function toggleKeyboardAliases(): boolean {
  aliasesEnabled = !aliasesEnabled;
  window.dispatchEvent(new Event('nfsu1-keyboard-change'));
  return aliasesEnabled;
}

export function keyboardLabel(code: string): string {
  const labels: Record<string, string> = {
    ArrowUp: '↑', ArrowDown: '↓', ArrowLeft: '←', ArrowRight: '→', Space: 'Space',
    AltLeft: 'Alt', AltRight: 'Right Alt',
    ShiftLeft: 'Left Shift', ShiftRight: 'Right Shift', ControlLeft: 'Left Ctrl', ControlRight: 'Right Ctrl',
    Backspace: 'Backspace', Escape: 'Esc',
  };
  return labels[code] ?? code.replace(/^Key|^Digit/, '').replace(/^Numpad/, 'Num ').replace(/([a-z])([A-Z])/g, '$1 $2');
}

/** Returns the destination KeyboardEvent.code only when this physical key is aliased.
 * Keep each keydown's result until keyup in the input adapter, even if settings change. */
export function translateKeyboardEvent(e: KeyboardEvent): string | undefined {
  if (!aliasesEnabled) return undefined;
  if (e.metaKey || e.isComposing) return undefined;
  for (const target of targetCodes) if (bindings[target] === e.code) return target;
  return undefined;
}

export function mountKeyboardControls(root: HTMLElement): void {
  root.dataset.nfsu2Ui = '';
  const group = document.createElement('div');
  group.className = 'group keyboard-settings';
  const heading = document.createElement('h3');
  heading.textContent = 'Keyboard controls';
  const help = document.createElement('p');
  help.className = 'muted';
  help.textContent = 'Choose a physical key for each action. These are the default game bindings; custom bindings in Options → Controls still apply. Changes are saved in this browser. Press F10 while playing to turn remapping off for text entry.';
  const rows = document.createElement('div');
  rows.className = 'keyboard-bindings';
  const status = document.createElement('p');
  status.className = 'keyboard-status muted';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const actions = document.createElement('div');
  actions.className = 'keyboard-actions';
  const wasd = document.createElement('button'), reset = document.createElement('button');
  wasd.type = reset.type = 'button';
  wasd.className = reset.className = 'btn';
  wasd.textContent = 'Use WASD';
  reset.textContent = 'Reset keyboard';
  actions.append(wasd, reset);
  group.append(heading, help, rows, actions, status);
  root.append(group);
  let cancelCapture: (() => void) | null = null;

  function save(next: Bindings, message: string): void {
    cancelCapture?.();
    bindings = next;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(bindings));
      status.textContent = message;
    } catch { status.textContent = `${message} Browser storage is unavailable; this change lasts for this page only.`; }
    // The input adapter releases held keys before applying a changed map.
    window.dispatchEvent(new Event('nfsu1-keyboard-change'));
    render();
  }

  function capture(target: Target, button: HTMLButtonElement): void {
    cancelCapture?.();
    button.textContent = 'Press a key…';
    button.classList.add('capturing');
    button.setAttribute('aria-pressed', 'true');
    status.textContent = 'Press a single key. Esc cancels. Browser and menu shortcuts are reserved.';
    const stop = () => {
      document.removeEventListener('keydown', onKey, true);
      window.removeEventListener('blur', stop);
      button.removeEventListener('blur', stop);
      button.textContent = keyboardLabel(bindings[target] ?? target);
      button.classList.remove('capturing');
      button.setAttribute('aria-pressed', 'false');
      cancelCapture = null;
    };
    const onKey = (e: KeyboardEvent) => {
      e.preventDefault(); e.stopImmediatePropagation();
      if (e.repeat || e.isComposing) return;
      if (e.code === 'Escape') { stop(); status.textContent = 'Key change cancelled.'; return; }
      const nitrousAlt = target === 'AltLeft' && (e.code === 'AltLeft' || e.code === 'AltRight');
      if (!validCode(e.code) || e.metaKey || (e.altKey && !nitrousAlt) || (e.ctrlKey && !e.code.startsWith('Control'))) {
        status.textContent = 'That key or shortcut is reserved. Choose another key, or press Esc to cancel.';
        return;
      }
      const conflict = targetCodes.find(other => other !== target && (bindings[other] ?? other) === e.code);
      if (conflict) {
        status.textContent = `${keyboardLabel(e.code)} is already assigned to ${actionFor(conflict)}. Choose another key, or reset that binding first.`;
        return;
      }
      const next = { ...bindings };
      if (e.code === target) delete next[target]; else next[target] = e.code;
      save(next, `${actionFor(target)} is now ${keyboardLabel(e.code)}.`);
    };
    cancelCapture = stop;
    document.addEventListener('keydown', onKey, true);
    window.addEventListener('blur', stop);
    button.addEventListener('blur', stop);
  }

  function render(): void {
    const focusedTarget = rows.contains(document.activeElement)
      ? (document.activeElement as HTMLElement).dataset.target : undefined;
    rows.replaceChildren();
    for (const target of targetCodes) {
      const row = document.createElement('div');
      row.className = 'keyboard-binding';
      const label = document.createElement('span');
      label.textContent = actionFor(target);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn key-binding';
      button.dataset.target = target;
      button.textContent = keyboardLabel(bindings[target] ?? target);
      button.setAttribute('aria-label', `Change key for ${actionFor(target)}`);
      button.setAttribute('aria-pressed', 'false');
      button.onclick = () => capture(target, button);
      row.append(label, button);
      rows.append(row);
    }
    if (focusedTarget) rows.querySelector<HTMLButtonElement>(`button[data-target="${focusedTarget}"]`)?.focus({ preventScroll: true });
    const keys = document.querySelector<HTMLElement>('#keys');
    if (keys) {
      let box = keys.querySelector<HTMLElement>('.keyboard-help');
      if (!box) { box = document.createElement('div'); box.className = 'keyboard-help'; keys.append(box); }
      const title = document.createElement('h3');
      title.textContent = 'Your keyboard';
      const note = document.createElement('p');
      note.textContent = 'Actions use the default game bindings. Change actions in the in-game Controls menu.';
      const list = document.createElement('dl');
      for (const target of targetCodes) {
        const term = document.createElement('dt'), value = document.createElement('dd');
        term.textContent = actionFor(target);
        value.textContent = keyboardLabel(bindings[target] ?? target);
        list.append(term, value);
      }
      box.replaceChildren(title, note, list);
    }
  }

  wasd.onclick = () => save({ ArrowUp: 'KeyW', ArrowDown: 'KeyS', ArrowLeft: 'KeyA', ArrowRight: 'KeyD' }, 'Throttle, brake and steering now use W, S, A and D.');
  reset.onclick = () => save({}, 'Original keyboard restored.');
  render();
}

function actionFor(target: Target): string {
  return TARGETS.find(item => item.code === target)!.action;
}
