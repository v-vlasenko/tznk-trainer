// Optional cloud sync of the progress store through Firebase (Google sign-in + Firestore).
// Loaded as an ES module after index.html's main script. Without firebase-config.js the
// app keeps working with localStorage only and the SDK is never downloaded.
const cfg = window.TZNK_FIREBASE;
const APP = window.TZNK_APP; // { getStore, setStore, rerenderHome, el, isHome }
if (cfg && APP) main().catch(e => console.warn('sync: disabled', e));

async function main() {
const SDK = 'https://www.gstatic.com/firebasejs/10.14.1/';
const [{ initializeApp }, { getAuth, GoogleAuthProvider, onAuthStateChanged, signInWithPopup, signInWithRedirect, signOut },
  { getFirestore, doc, collection, getDocs, setDoc, onSnapshot, serverTimestamp }] = await Promise.all([
  import(SDK + 'firebase-app.js'), import(SDK + 'firebase-auth.js'), import(SDK + 'firebase-firestore.js')]);

const fb = initializeApp(cfg.firebase);
const auth = getAuth(fb);
const db = getFirestore(fb);
const provider = new GoogleAuthProvider();
provider.setCustomParameters({ prompt: 'select_account' });

let user = null;
let unsubscribe = null;
let pushTimer = null;
let lastPushed = '';
const slot = document.getElementById('account');
const { el } = APP;

// ---------- merge ----------
// Two copies of the store (this device and the cloud) may both have changed.
// Union of histories, max of counters: nothing a device recorded is ever lost.
function mergeStores(a, b) {
  const out = { attempts: [], errors: {}, drill: {}, sessions: [], inProgress: null };
  const byDate = new Map();
  for (const x of [...(a.attempts || []), ...(b.attempts || [])]) byDate.set(x.date, x);
  out.attempts = [...byDate.values()].sort((x, y) => x.date.localeCompare(y.date));
  const sess = new Map();
  for (const x of [...(a.sessions || []), ...(b.sessions || [])]) sess.set(x.date, x);
  out.sessions = [...sess.values()].sort((x, y) => x.date.localeCompare(y.date));
  for (const k of new Set([...Object.keys(a.drill || {}), ...Object.keys(b.drill || {})])) {
    const x = (a.drill || {})[k] || { ok: 0, bad: 0 }, y = (b.drill || {})[k] || { ok: 0, bad: 0 };
    out.drill[k] = { ok: Math.max(x.ok, y.ok), bad: Math.max(x.bad, y.bad) };
  }
  for (const k of new Set([...Object.keys(a.errors || {}), ...Object.keys(b.errors || {})])) {
    const x = (a.errors || {})[k], y = (b.errors || {})[k];
    out.errors[k] = !x ? y : !y ? x : { count: Math.max(x.count, y.count), last: [x.last, y.last].sort().pop() };
  }
  const p = [a.inProgress, b.inProgress].filter(Boolean).sort((x, y) => (x.started || '').localeCompare(y.started || ''));
  out.inProgress = p.pop() || null;
  return out;
}

function fingerprint(store) {
  const { attempts, errors, drill, sessions, inProgress } = store;
  return JSON.stringify({ attempts, errors, drill, sessions, inProgress });
}

// ---------- cloud ----------
function userDoc() { return doc(db, 'users', user.uid); }

async function pushNow() {
  if (!user) return;
  const store = APP.getStore();
  const fp = fingerprint(store);
  if (fp === lastPushed) return;
  lastPushed = fp;
  const { attempts, errors, drill, sessions, inProgress } = store;
  await setDoc(userDoc(), {
    attempts, errors, drill, sessions: sessions || [], inProgress,
    name: user.displayName || '', email: user.email || '', photo: user.photoURL || '',
    updatedAt: serverTimestamp(), device: navigator.userAgent.slice(0, 80),
  });
  setStatus('');
}

function schedulePush() {
  if (!user) return;
  setStatus('…');
  clearTimeout(pushTimer);
  pushTimer = setTimeout(() => pushNow().catch(e => setStatus('помилка синхронізації', e)), 1500);
}

function listen() {
  if (unsubscribe) unsubscribe();
  unsubscribe = onSnapshot(userDoc(), snap => {
    if (snap.metadata.hasPendingWrites) return; // our own write echoing back
    const remote = snap.exists() ? snap.data() : null;
    const local = APP.getStore();
    const merged = remote ? mergeStores(local, remote) : local;
    const fp = fingerprint(merged);
    const changed = fp !== fingerprint(local);
    if (changed) APP.setStore(merged);
    if (fp !== lastPushed) schedulePush(); // upload the union so both sides converge
    else setStatus('');
    if (changed && APP.isHome()) APP.rerenderHome();
  }, e => setStatus('немає доступу до хмари', e));
}

// ---------- UI ----------
function setStatus(text, err) {
  if (err) console.warn('sync:', err);
  const s = slot.querySelector('.sync-status');
  if (s) s.textContent = text;
}

function renderSlot() {
  if (!user) {
    slot.replaceChildren(el('button', { class: 'btn small', onclick: signIn }, 'Увійти через Google'));
    return;
  }
  slot.replaceChildren(
    el('span', { class: 'acct', title: user.email || '' },
      user.photoURL ? el('img', { src: user.photoURL, alt: '', referrerpolicy: 'no-referrer' }) : null,
      el('span', { class: 'name' }, user.displayName || user.email || 'Акаунт'),
      el('span', { class: 'sync-status muted small' }, '')),
    isAdmin() ? el('button', { class: 'btn small', onclick: showAll }, 'Прогрес усіх') : null,
    el('button', { class: 'btn small', onclick: () => signOut(auth) }, 'Вийти'));
}

async function signIn() {
  try { await signInWithPopup(auth, provider); }
  catch (e) {
    if (e.code === 'auth/popup-blocked' || e.code === 'auth/popup-closed-by-user' && /Mobi/.test(navigator.userAgent)) {
      await signInWithRedirect(auth, provider);
    } else { alert('Не вдалося увійти: ' + (e.code || e.message)); console.warn(e); }
  }
}

function isAdmin() { return !!user && (cfg.admins || []).includes(user.email); }

// Admin view: one card per signed-in person with the same numbers as the home page.
async function showAll() {
  const snaps = await getDocs(collection(db, 'users'));
  const rows = [];
  snaps.forEach(s => rows.push({ id: s.id, ...s.data() }));
  rows.sort((a, b) => (b.updatedAt?.toMillis?.() || 0) - (a.updatedAt?.toMillis?.() || 0));
  const fmt = ts => ts?.toDate ? ts.toDate().toLocaleString('uk-UA', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';
  const cards = rows.map(u => {
    const drill = Object.values(u.drill || {});
    const ok = drill.reduce((s, d) => s + d.ok, 0), bad = drill.reduce((s, d) => s + d.bad, 0);
    const best = (u.attempts || []).length ? Math.max(...u.attempts.map(a => a.score)) : null;
    const last = (u.sessions || []).slice(-5).reverse();
    return el('div', { class: 'card', style: 'margin-bottom:12px' },
      el('div', { class: 'row' }, u.photo ? el('img', { src: u.photo, alt: '', referrerpolicy: 'no-referrer', style: 'width:28px;height:28px;border-radius:50%' }) : null,
        el('b', {}, u.name || u.email || u.id), el('span', { class: 'muted small' }, u.email || ''), el('span', { class: 'spacer' }), el('span', { class: 'muted small' }, 'активність: ' + fmt(u.updatedAt))),
      el('div', { class: 'stats', style: 'margin-top:12px' },
        el('div', { class: 'stat' }, el('div', { class: 'v' }, (u.attempts || []).length), el('div', { class: 'l' }, 'симуляцій')),
        el('div', { class: 'stat' }, el('div', { class: 'v' }, best === null ? '—' : `${best}/33`), el('div', { class: 'l' }, 'найкращий бал')),
        el('div', { class: 'stat' }, el('div', { class: 'v' }, ok + bad ? `${Math.round(100 * ok / (ok + bad))}%` : '—'), el('div', { class: 'l' }, `точність у тренажері (${ok + bad} відповідей)`)),
        el('div', { class: 'stat' }, el('div', { class: 'v' }, Object.keys(u.errors || {}).length), el('div', { class: 'l' }, 'помилок у списку'))),
      last.length ? el('div', { class: 'list' }, ...last.map(s => el('div', { class: 'item' },
        el('span', {}, el('b', {}, s.title), ' ', el('span', { class: 'muted' }, new Date(s.date).toLocaleDateString('uk-UA', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }))),
        el('span', { class: 'pill ' + (s.ok === s.total ? 'ok' : '') }, `${s.ok}/${s.total}`)))) : null);
  });
  document.getElementById('app').replaceChildren(
    el('h2', { class: 'sec' }, 'Прогрес усіх, хто входив'),
    ...(cards.length ? cards : [el('p', { class: 'muted' }, 'Поки ніхто не входив.')]),
    el('button', { class: 'btn', onclick: APP.rerenderHome }, 'На головну'));
  window.scrollTo({ top: 0 });
}

let ready = false;
onAuthStateChanged(auth, u => {
  user = u;
  ready = true;
  lastPushed = '';
  if (unsubscribe) { unsubscribe(); unsubscribe = null; }
  renderSlot();
  if (user) listen();
  if (APP.isHome()) APP.rerenderHome(); // show or hide the sign-in offer
});

// index.html calls schedulePush after every local change and reads the rest for the home page.
window.TZNK_SYNC = { schedulePush, mergeStores, signIn, isSignedIn: () => !!user, isReady: () => ready };
}
