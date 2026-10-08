// Tests for the logic inside web/phone.html: the Zwift Click decoders and the request queue.
// Run: node --test tests/js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '..', '..', 'pedalator', 'web', 'phone.html'), 'utf8');

function between(startMarker, endMarker) {
  const a = html.indexOf(startMarker), b = html.indexOf(endMarker);
  assert.ok(a >= 0 && b > a, `markers not found: ${startMarker} .. ${endMarker}`);
  return html.slice(a, b);
}

// ---------------------------------------------------------------- Click decoders (pure functions)
const decoders = new Function(between('// <decoders>', '// </decoders>') +
  '; return { actionsFrom, rawFrom, fields, varint };')();
const { actionsFrom, rawFrom } = decoders;

const ALL = 0xFFFFFFFF;
function enc(v) { const o = []; while (v >= 128) { o.push((v % 128) | 128); v = Math.floor(v / 128); } o.push(v); return o; }
const v2 = map => new Uint8Array([0x23, 0x08, ...enc(map >>> 0)]);
const v1 = (plus, minus) => new Uint8Array([0x37, 0x08, plus, 0x10, minus]);
const list = s => (s === null ? null : [...s].sort());

test('Click v2: a pressed button is a cleared bit', () => {
  assert.deepEqual(list(rawFrom(0x23, v2(ALL))), []);
  for (const [name, bit] of [['LEFT', 1], ['UP', 2], ['RIGHT', 4], ['DOWN', 8], ['A', 16], ['B', 32], ['Y', 64], ['Z', 256],
                             ['MINUS', 512], ['PLUS', 8192]]) {
    assert.deepEqual(list(rawFrom(0x23, v2(ALL & ~bit))), [name], name);
  }
});

test('Click v2: real frames recorded from a controller', () => {
  assert.deepEqual(list(rawFrom(0x23, Uint8Array.from([0x23, 0x08, 0xfe, 0xff, 0xff, 0xff, 0x0f]))), ['LEFT']);
  assert.deepEqual(list(rawFrom(0x23, Uint8Array.from([0x23, 0x08, 0xfb, 0xff, 0xff, 0xff, 0x0f]))), ['RIGHT']);
  assert.deepEqual(list(rawFrom(0x23, Uint8Array.from([0x23, 0x08, 0xff, 0xff, 0xff, 0xff, 0x0f]))), []);
});

test('Click v2: several buttons at once', () => {
  assert.deepEqual(list(rawFrom(0x23, v2(ALL & ~32 & ~2))), ['B', 'UP']);
});

test('Click v1: minus and plus steer', () => {
  assert.deepEqual(list(rawFrom(0x37, v1(1, 1))), []);
  assert.deepEqual(list(rawFrom(0x37, v1(1, 0))), ['LEFT']);
  assert.deepEqual(list(rawFrom(0x37, v1(0, 1))), ['RIGHT']);
  assert.deepEqual(list(actionsFrom(0x37, v1(1, 0))), ['left']);
});

test('driving actions for the keys target', () => {
  assert.deepEqual(list(actionsFrom(0x23, v2(ALL & ~256))), ['left']);      // Z steers left
  assert.deepEqual(list(actionsFrom(0x23, v2(ALL & ~16))), ['right']);      // A steers right
  assert.deepEqual(list(actionsFrom(0x23, v2(ALL & ~32))), ['brake']);      // B brakes
  assert.deepEqual(list(actionsFrom(0x23, v2(ALL & ~64))), []);             // Y does nothing here
});

test('Click v2: minus and plus are the difficulty buttons and do not steer', () => {
  assert.deepEqual(list(actionsFrom(0x23, v2(ALL & ~512))), []);            // minus
  assert.deepEqual(list(actionsFrom(0x23, v2(ALL & ~8192))), []);           // plus
  assert.deepEqual(list(rawFrom(0x23, v2(ALL & ~512))), ['MINUS']);         // but the PC still hears them
  assert.deepEqual(list(rawFrom(0x23, v2(ALL & ~8192))), ['PLUS']);
});

test('battery, keep-alive and unknown messages are ignored', () => {
  assert.equal(rawFrom(0x19, new Uint8Array([0x19, 0, 0x64])), null);
  assert.equal(actionsFrom(0x15, new Uint8Array([0x15])), null);
  assert.equal(rawFrom(0x23, new Uint8Array([0x23])), null);                // no ButtonMap field: not a button frame
});

// ---------------------------------------------------------------- vectors shared with the Python decoder
test('the decoder agrees with tests/vectors/click_frames.json (the same file the Python tests use)', () => {
  const vectors = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'vectors', 'click_frames.json'), 'utf8'));
  assert.ok(vectors.length > 10);
  for (const v of vectors) {
    const bytes = Uint8Array.from(v.hex.split(' ').map(h => parseInt(h, 16)));
    const raw = rawFrom(bytes[0], bytes), act = actionsFrom(bytes[0], bytes);
    if (v.raw === null) { assert.equal(raw, null, v.name); assert.equal(act, null, v.name); continue; }
    assert.deepEqual(list(raw), v.raw, v.name + ' (raw)');
    assert.deepEqual(list(act), v.actions, v.name + ' (actions)');
  }
});

// ---------------------------------------------------------------- the request queue
const netCode = between('let postFails = 0', 'function setPc(ok)');

function makeNet() {
  const calls = [], lines = [];
  const env = { mode: 'ok', delay: 20, pcShown: null };
  const fetch = url => new Promise((res, rej) => {
    calls.push(url);
    setTimeout(() => (env.mode === 'ok' ? res({ ok: true, status: 200 }) : rej(new TypeError('Failed to fetch'))), env.delay);
  });
  const api = new Function('logLines', '$', 'q', 'setPc', 'navigator', 'fetch', 'performance', 'AbortController', 't',
    netCode + '; return { post, state: () => ({ postFails, dataBusy }) };')(
    lines, () => ({ textContent: '', scrollTop: 0 }), p => p + '?t=x', ok => { env.pcShown = ok; },
    { onLine: true }, fetch, { now: () => Date.now() }, AbortController, (s, ...a) => s + ' ' + a.join(' '));
  return { api, calls, lines, env };
}

const wait = ms => new Promise(r => setTimeout(r, ms));

test('trainer packets are coalesced: while one is in flight only the newest waits', async () => {
  const { api, calls } = makeNet();
  for (let i = 0; i < 6; i++) api.post('/phone/data', { hex: 'p' + i });
  await wait(150);
  assert.equal(calls.filter(c => c.startsWith('/phone/data')).length, 2);
  assert.equal(api.state().dataBusy, false);
});

test('other requests are never merged', async () => {
  const { api, calls } = makeNet();
  api.post('/phone/buttons', { raw: ['A'] });
  api.post('/phone/buttons', { raw: [] });
  await wait(80);
  assert.equal(calls.length, 2);
});

test('failures are counted, shown after three, probed after ten, and forgotten on success', async () => {
  const { api, calls, env, lines } = makeNet();
  env.mode = 'fail';
  for (let i = 0; i < 12; i++) await api.post('/phone/status', { kind: 'log' });
  assert.equal(api.state().postFails, 12);
  assert.equal(env.pcShown, false);
  assert.ok(calls.includes('/phone/ping?t=x'), 'a probe was sent');
  assert.ok(lines.length >= 1);
  env.mode = 'ok';
  await api.post('/phone/status', { kind: 'log' });
  assert.equal(api.state().postFails, 0);
  assert.equal(env.pcShown, true);
});
