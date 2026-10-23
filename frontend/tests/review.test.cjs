const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
function load(file,deps={},globals={}){
  const source=fs.readFileSync(path.join(__dirname,'../src',file),'utf8').replace('import.meta.env.VITE_API_BASE_URL','undefined');
  const code=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const exports={};vm.runInNewContext(code,{exports,require:name=>deps[name],...globals});return exports;
}
const helpers=load('notePresentation.ts');
const note={id:'first',patient_id:'SYN-REVIEW',diagnoses:'First, qualifier, Second',medications:'Drug 1,000 mg',follow_ups:'Return',urgency:'routine',confidence:0.8,warning:'Original warning',created_at:'2026-01-01T12:00:00Z'};
const source={note_id:'first',source_id:'source-id',kind:'text',availability:'available',provenance:'submitted',original_filename:null,mime_type:'text/plain',byte_size:40,sha256:'a'.repeat(64),stored_at:'2026-01-01T12:00:00Z',original_text:'  Original synthetic text\n<script>literal text</script>  ',unavailable_reason:null,ai_result:{diagnoses:['First, qualifier','Second'],medications:['Drug 1,000 mg'],follow_ups:['Return'],urgency:'routine',confidence:0.8},model_name:'gpt-4o',prompt_version:'v1',extraction_schema_version:1,review_status:'unreviewed'};
class ApiError extends Error{constructor(message,status){super(message);this.status=status;}}
const tick=()=>new Promise(r=>setImmediate(r));
function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
function materialize(node){
  if(!node||typeof node!=='object')return node;
  if(Array.isArray(node))return node.map(materialize);
  if(typeof node.type==='function'&&node.type.name!=='ImageSourcePreview')return materialize(node.type(node.props));
  return {...node,props:{...node.props,children:materialize(node.props?.children)}};
}
function find(node,predicate){if(!node||typeof node!=='object')return;if(Array.isArray(node))return node.map(n=>find(n,predicate)).find(Boolean);if(predicate(node))return node;return find(node.props?.children,predicate);}
function content(node){if(node==null||typeof node==='boolean')return '';if(typeof node!=='object')return String(node);if(Array.isArray(node))return node.map(content).join(' ');return content(node.props?.children);}
function harness(overrides={}){
  const slots=[],effects=[],cleanups=[];let cursor=0;
  const react={useState(initial){const i=cursor++;if(!(i in slots))slots[i]=typeof initial==='function'?initial():initial;return [slots[i],v=>slots[i]=typeof v==='function'?v(slots[i]):v];},useRef(initial){const [ref]=react.useState(()=>({current:initial}));return ref;},useEffect(fn,deps){const i=cursor++;const old=slots[i];if(!old||deps.some((v,j)=>v!==old[j])){slots[i]=deps;effects.push({i,fn});}}};
  const calls=[],created=[],revoked=[];let unauthorized=0;
  const api={note:async(token,id,signal)=>{calls.push(['note',token,id,signal]);return {...note,id};},source:async(token,id,signal)=>{calls.push(['source',token,id,signal]);return {...source,note_id:id};},sourceContent:async(token,id,signal)=>{calls.push(['content',token,id,signal]);return new Blob(['synthetic bytes'],{type:'image/png'});},...overrides};
  const jsx=(type,props)=>({type,props});
  const module=load('DocumentReview.tsx',{react,'react/jsx-runtime':{jsx,jsxs:jsx,Fragment:'fragment'},'lucide-react':{},'./api':{api,ApiError},'./notePresentation':helpers},{AbortController,URL:{createObjectURL:blob=>{const url=`blob:source-${created.length+1}`;created.push({url,blob});return url;},revokeObjectURL:url=>revoked.push(url)}});
  let props={noteId:'first',token:'session-token',onUnauthorized:()=>unauthorized++,onBack(){}};
  return {api,calls,created,revoked,get unauthorized(){return unauthorized;},render(next={}){props={...props,...next};cursor=0;return materialize(module.DocumentReview(props));},async flush(){for(const {i,fn} of effects.splice(0)){cleanups[i]?.();cleanups[i]=fn();}await tick();return this.render();},dispose(){for(const fn of cleanups)fn?.();},preview(props){cursor=0;return materialize(module.ImageSourcePreview(props));}};
}
test('loading remains visible while requests are pending',async()=>{
  const pending=deferred();const h=harness({source:()=>pending.promise});assert.match(content(h.render()),/Loading original document/);assert.ok(find(await h.flush(),n=>n.props?.role==='status'));h.dispose();pending.resolve(source);await tick();assert.equal(h.created.length,0);
});
test('text and immutable structured output preserve exact text and list boundaries without editing controls',async()=>{
  const h=harness();h.render();const tree=await h.flush();assert.equal(find(tree,n=>n.type==='pre').props.children,source.original_text);assert.ok(find(tree,n=>n.type==='li'&&n.props.children==='First, qualifier'));assert.match(content(tree),/Unreviewed/);assert.match(content(tree),/Original AI output/);assert.equal(find(tree,n=>n.type==='textarea'||n.props?.contentEditable),undefined);assert.equal(find(tree,n=>n.type==='button'&&/^(Save|Approve|Export)/.test(content(n))),undefined);assert.equal(h.calls.some(c=>c[0]==='content'),false);h.dispose();
});
test('protected images use bearer session and object URLs that are revoked during cleanup',async()=>{
  const h=harness({source:async()=>({...source,kind:'image',mime_type:'image/png',original_text:null,original_filename:'synthetic.png'})});h.render();const tree=await h.flush();assert.equal(find(tree,n=>n.type?.name==='ImageSourcePreview').props.url,'blob:source-1');const request=h.calls.find(c=>c[0]==='content');assert.deepEqual(request.slice(1,3),['session-token','first']);assert.equal(request[3].aborted,false);h.dispose();assert.equal(request[3].aborted,true);assert.deepEqual(h.revoked,['blob:source-1']);
});
test('historical unavailable sources are explicit and never fetch or fabricate images',async()=>{
  const h=harness({source:async()=>({...source,kind:'unknown',availability:'unavailable',original_text:null,ai_result:null,unavailable_reason:'Historical image uploads were not retained.'})});h.render();const tree=await h.flush();assert.match(content(tree),/Original source unavailable/);assert.match(content(tree),/not retained/);assert.match(content(tree),/Legacy extraction/);assert.ok(find(tree,n=>n.type==='p'&&n.props.children===note.diagnoses));assert.equal(h.calls.some(c=>c[0]==='content'),false);assert.equal(h.created.length,0);h.dispose();
});
for(const failure of [401,404,500,'network'])test(`metadata ${failure} errors have correct authorization and retry behavior`,async()=>{
  const h=harness({source:async()=>{throw failure==='network'?new TypeError('offline'):new ApiError('failure',failure);}});h.render();let tree=await h.flush();
  if(failure===401){assert.equal(h.unauthorized,1);assert.equal(find(tree,n=>n.type==='pre'),undefined);}else{assert.equal(h.unauthorized,0);assert.ok(find(tree,n=>n.props?.role==='alert'));if(failure===404)assert.match(content(tree),/do not have access/);h.api.source=async()=>source;find(tree,n=>n.type==='button'&&content(n)==='Retry document loading').props.onClick();h.render();tree=await h.flush();assert.equal(find(tree,n=>n.type==='pre').props.children,source.original_text);}h.dispose();
});
for(const status of [401,404,500])test(`image ${status} failure handles auth while retaining safe error feedback`,async()=>{
  const h=harness({source:async()=>({...source,kind:'image',original_text:null}),sourceContent:async()=>{throw new ApiError('failure',status);}});h.render();const tree=await h.flush();assert.equal(h.unauthorized,status===401?1:0);assert.equal(h.created.length,0);if(status!==401){assert.ok(find(tree,n=>n.props?.role==='alert'));assert.match(content(tree),/Original AI output/);}h.dispose();
});
test('late image completion after leaving cannot leak an object URL',async()=>{
  const pending=deferred();const h=harness({source:async()=>({...source,kind:'image'}),sourceContent:()=>pending.promise});h.render();await h.flush();h.dispose();pending.resolve(new Blob(['late'],{type:'image/png'}));await tick();assert.equal(h.created.length,0);assert.equal(h.unauthorized,0);
});
test('switching documents immediately hides previous content and releases its image URL',async()=>{
  const h=harness({source:async()=>({...source,kind:'image'})});h.render();await h.flush();assert.match(content(h.render({noteId:'second'})),/Loading original document/);const tree=await h.flush();assert.equal(find(tree,n=>n.type?.name==='ImageSourcePreview').props.url,'blob:source-2');assert.deepEqual(h.revoked,['blob:source-1']);h.dispose();assert.deepEqual(h.revoked,['blob:source-1','blob:source-2']);
});
test('a late 401 from a parallel request still invalidates the session',async()=>{
  const pending=deferred();const h=harness({note:async()=>{throw new ApiError('server',500);},source:()=>pending.promise});h.render();await h.flush();pending.reject(new ApiError('expired',401));await tick();assert.equal(h.unauthorized,1);h.dispose();
});
test('zoom and source details provide image inspection without editing',()=>{
  const h=harness();const props={source:{...source,kind:'image',original_filename:'synthetic.png'},url:'blob:preview',patient:'SYN-REVIEW'};let tree=h.preview(props);assert.equal(find(tree,n=>n.type==='img').props.style.width,'100%');find(tree,n=>n.props?.['aria-label']==='Zoom in').props.onClick();tree=h.preview(props);assert.equal(find(tree,n=>n.type==='img').props.style.width,'125%');find(tree,n=>n.type==='img').props.onLoad({currentTarget:{naturalWidth:15,naturalHeight:10}});tree=h.preview(props);assert.match(content(tree),/15 × 10 pixels/);assert.ok(find(tree,n=>n.type==='summary'&&content(n)==='Image details'));find(tree,n=>n.type==='button'&&content(n)==='Fit image').props.onClick();tree=h.preview(props);assert.equal(find(tree,n=>n.type==='img').props.style.width,'100%');assert.equal(find(tree,n=>n.props?.['aria-label']==='Zoom out').props.disabled,true);
});
test('binary API uses bearer header, encodes IDs, disables cache, and preserves response bytes',async()=>{
  const calls=[],bytes=new Uint8Array([0,1,2,255]);const {api}=load('api.ts',{}, {Headers,fetch:async(url,init)=>{calls.push({url,init});return new Response(bytes,{headers:{'Content-Type':'image/png'}});}});const signal=new AbortController().signal;const blob=await api.sourceContent('secret','id/with space',signal);assert.deepEqual(new Uint8Array(await blob.arrayBuffer()),bytes);assert.equal(blob.type,'image/png');assert.equal(calls[0].url,'/api/notes/id%2Fwith%20space/source/content');assert.equal(calls[0].init.headers.get('Authorization'),'Bearer secret');assert.equal(calls[0].init.cache,'no-store');assert.equal(calls[0].init.signal,signal);
});
for(const status of [401,404,500])test(`binary API preserves HTTP ${status} as an ApiError`,async()=>{
  const module=load('api.ts',{}, {Headers,fetch:async()=>new Response(JSON.stringify({detail:'source failure'}),{status})});await assert.rejects(module.api.sourceContent('token','note'),e=>e instanceof module.ApiError&&e.status===status);
});
