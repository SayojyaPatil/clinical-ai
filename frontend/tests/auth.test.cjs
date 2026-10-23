const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const jwt = exp => `header.${Buffer.from(JSON.stringify({ exp })).toString('base64url')}.signature`;
const valid = jwt(Date.now() / 1000 + 3600);

function harness(stored, notes = async () => [], overrides = {}) {
  const storage = new Map(stored ? [['clinical-ai.session', JSON.stringify(stored)]] : []);
  const sessionStorage = { getItem: k => storage.get(k) ?? null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k) };
  function load(file, dependencies = {}) {
    const source = fs.readFileSync(path.join(__dirname, '../src', file), 'utf8');
    const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
    const exports = {};
    vm.runInNewContext(code, { exports, require: name => dependencies[name], sessionStorage, atob, Date, console });
    return exports;
  }
  const session = load('session.ts');
  const states = []; let cursor = 0; let effects = []; let vnode;
  const react = {
    useState(initial) { const i = cursor++; if (!(i in states)) states[i] = typeof initial === 'function' ? initial() : initial; return [states[i], value => { states[i] = typeof value === 'function' ? value(states[i]) : value; }]; },
    useRef(initial) { const [ref] = react.useState(() => ({ current: initial })); return ref; },
    useMemo(fn) { return fn(); }, useCallback(fn, deps) { return react.useMemoized(fn, deps); },
    useMemoized(fn, deps) { const i = cursor++; const prev = states[i]; if (!prev || deps.some((v,j) => v !== prev.deps[j])) states[i] = { fn, deps }; return states[i].fn; },
    useEffect(fn, deps) { const i = cursor++; const prev = states[i]; if (!prev || deps.some((v,j) => v !== prev[j])) { states[i] = deps; effects.push(fn); } },
  };
  class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
  const calls = [];
  const api = { notes: token => { calls.push(token); return notes(ApiError); }, ...overrides };
  const jsx = (type, props) => ({ type, props });
  const App = load('App.tsx', { react, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'fragment' }, 'lucide-react': {}, './api': { api, ApiError }, './session': session, './Result': {}, './ImageUpload': {}, './NavigationDialog': {}, './DocumentReview': { DocumentReview: function DocumentReview() {} }, './notePresentation': load('notePresentation.ts') }).default;
  return { session, storage, calls, ApiError,
    render() { cursor = 0; vnode = App(); return vnode; },
    async flush() { const pending = effects; effects = []; pending.forEach(fn => fn()); await new Promise(resolve => setImmediate(resolve)); return this.render(); },
  };
}
function find(node, predicate) {
  if (!node || typeof node !== 'object') return undefined;
  if (predicate(node)) return node;
  return [node.props?.children].flat(Infinity).map(n => find(n, predicate)).find(Boolean);
}
test('restores a valid JWT, verifies via notes, and displays loading first', async () => {
  const h = harness({ token: valid, username: 'demo' });
  assert.ok(find(h.render(), n => n.props?.role === 'status'));
  const tree = await h.flush();
  assert.deepEqual(h.calls, [valid]);
  assert.ok(find(tree, n => n.type === 'header'));
  assert.equal(h.storage.size, 1);
});
test('expired, missing-expiry, and malformed sessions are cleared before API calls', async () => {
  for (const token of [jwt(1), jwt(undefined), 'bad', jwt('99999999999')]) {
    const h = harness({ token, username: 'demo' });
    assert.equal(typeof h.render().props.onAuth, 'function');
    await h.flush(); assert.equal(h.calls.length, 0); assert.equal(h.storage.size, 0);
  }
});
test('a 401 during restoration clears storage and shows login', async () => {
  const h = harness({ token: valid, username: 'demo' }, async E => { throw new E('Unauthorized', 401); });
  h.render(); const tree = await h.flush();
  assert.equal(typeof tree.props.onAuth, 'function'); assert.equal(h.storage.size, 0);
});
for (const kind of ['network', '500']) test(`${kind} errors retain authentication and show a recoverable error`, async () => {
  const h = harness({ token: valid, username: 'demo' }, async E => { throw kind === 'network' ? new TypeError('Failed to fetch') : new E('Server error', 500); });
  h.render(); const tree = await h.flush();
  assert.ok(find(tree, n => n.type === 'header'));
  assert.ok(find(tree, n => n.props?.role === 'alert')); assert.equal(h.storage.size, 1);
});
test('successful login persists credentials; explicit logout clears storage and account state', async () => {
  const h = harness();
  h.render().props.onAuth(valid, 'demo');
  h.render(); let tree = await h.flush();
  assert.deepEqual(JSON.parse(h.storage.get('clinical-ai.session')), { token: valid, username: 'demo' });
  // The sidebar logout button contains the username and has a direct onClick handler.
  const logout = find(tree, n => n.type === 'button' && find(n, c => c.type === 'span' && c.props.children === 'demo'));
  assert.ok(logout); logout.props.onClick(); tree = h.render();
  assert.equal(typeof tree.props.onAuth, 'function'); assert.equal(h.storage.size, 0);
});
test('a request completing after logout cannot restore old account data', async () => {
  let resolve;
  const h = harness(undefined, () => new Promise(r => { resolve = r; }));
  h.render().props.onAuth(valid, 'demo'); h.render(); let tree = await h.flush();
  const logout = find(tree, n => n.type === 'button' && find(n, c => c.type === 'span' && c.props.children === 'demo'));
  logout.props.onClick(); resolve([{ id: 'old-account' }]);
  tree = await h.flush(); assert.equal(typeof tree.props.onAuth, 'function'); assert.equal(h.storage.size, 0);
});

test('AI submissions are locked synchronously and report success', async () => {
  let resolve; let submissions=0;
  const h=harness({token:valid,username:'demo'},async()=>[],{analyzeText:()=>{submissions++;return new Promise(r=>resolve=r);}});
  h.render();let tree=await h.flush();
  find(tree,n=>n.props?.id==='patient').props.onChange({target:{value:'DEMO-1'}});
  find(tree,n=>n.props?.id==='note').props.onChange({target:{value:'A sufficiently detailed synthetic clinical note.'}});
  tree=h.render();const submit=find(tree,n=>n.type==='form').props.onSubmit;
  const first=submit({preventDefault(){}});await submit({preventDefault(){}});
  assert.equal(submissions,1);tree=h.render();assert.equal(find(tree,n=>n.type==='fieldset').props.disabled,true);
  resolve({id:'1',patient_id:'DEMO-1'});await first;tree=h.render();
  assert.ok(find(tree,n=>n.props?.role==='status'&&n.props.children==='Analysis complete and saved to your account.'));
  assert.equal(find(tree,n=>n.type==='fieldset').props.disabled,false);
});
test('AI failures keep inputs and authentication, release the lock, and avoid a history retry action', async () => {
  const h=harness({token:valid,username:'demo'},async()=>[],{analyzeText:async()=>{throw new Error('Server unavailable');}});
  h.render();let tree=await h.flush();
  find(tree,n=>n.props?.id==='patient').props.onChange({target:{value:'DEMO-1'}});
  find(tree,n=>n.props?.id==='note').props.onChange({target:{value:'A sufficiently detailed synthetic clinical note.'}});
  tree=h.render();await find(tree,n=>n.type==='form').props.onSubmit({preventDefault(){}});tree=h.render();
  assert.equal(find(tree,n=>n.props?.id==='patient').props.value,'DEMO-1');
  assert.equal(find(tree,n=>n.type==='fieldset').props.disabled,false);
  assert.ok(find(tree,n=>n.props?.role==='alert'));assert.equal(h.storage.size,1);
  assert.equal(find(tree,n=>n.type==='button'&&n.props.children==='Retry loading history'),undefined);
});
test('history expands details in the matching row and search hides unmatched details', async () => {
  const note={id:'1',patient_id:'DEMO-1',diagnoses:'Example',created_at:'2026-10-23T12:00:00Z',urgency:'routine'};
  const h=harness({token:valid,username:'demo'},async()=>[note]);h.render();let tree=await h.flush();
  find(tree,n=>n.type==='button'&&find(n,c=>c.type==='span'&&c.props.children==='DEMO-1')).props.onClick();tree=h.render();
  assert.ok(find(tree,n=>n.type==='article'&&find(n,c=>c.props?.embedded===true)));
  assert.equal(find(tree,n=>n.props?.['aria-expanded']===true).props['aria-controls'],'history-1');
  find(tree,n=>n.props?.['aria-label']==='Filter by patient reference').props.onChange({target:{value:'missing'}});tree=h.render();
  assert.equal(find(tree,n=>n.props?.embedded===true),undefined);
  assert.ok(find(tree,n=>n.type==='h2'&&n.props.children==='No matching analyses'));
});

test('history opens a read-only document review and its 401 handler clears the session', async () => {
  const note={id:'review-id',patient_id:'SYN-REVIEW',diagnoses:'Synthetic diagnosis',created_at:'2026-01-01',urgency:'routine'};
  const h=harness({token:valid,username:'demo'},async()=>[note]);h.render();let tree=await h.flush();
  find(tree,n=>n.type==='button'&&find(n,c=>c.type==='span'&&c.props.children==='SYN-REVIEW')).props.onClick();tree=h.render();
  find(tree,n=>n.props?.['aria-label']==='Open document review for SYN-REVIEW').props.onClick();tree=h.render();
  let review=find(tree,n=>n.type?.name==='DocumentReview');assert.equal(review.props.noteId,'review-id');assert.equal(review.props.token,valid);
  review.props.onBack();tree=h.render();assert.ok(find(tree,n=>n.props?.['aria-label']==='Filter by patient reference'));
  find(tree,n=>n.props?.['aria-label']==='Open document review for SYN-REVIEW').props.onClick();tree=h.render();
  review=find(tree,n=>n.type?.name==='DocumentReview');review.props.onUnauthorized();tree=h.render();
  assert.equal(typeof tree.props.onAuth,'function');assert.equal(h.storage.size,0);
});
