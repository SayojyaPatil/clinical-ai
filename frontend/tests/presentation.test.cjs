const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
function load(file,deps={},globals={}){
  const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const exports={};vm.runInNewContext(code,{exports,require:name=>deps[name],...globals});return exports;
}
const helpers=load('notePresentation.ts');
const note={id:'abc',patient_id:'DEMO-1',diagnoses:'First diagnosis, Second diagnosis',medications:'Drug 1,000 mg; Other drug 10 mg',follow_ups:'First visit\nSecond visit',urgency:'routine',confidence:.8234,warning:'Full original warning\nSecond warning line',created_at:'2026-10-23T12:00:00Z'};
test('formats API comma-separated, semicolon-separated and multiline fields without splitting numeric doses',()=>{
  assert.deepEqual(Array.from(helpers.fieldItems(note.diagnoses)),['First diagnosis','Second diagnosis']);
  assert.deepEqual(Array.from(helpers.fieldItems(note.medications)),['Drug 1,000 mg','Other drug 10 mg']);
  assert.deepEqual(Array.from(helpers.fieldItems(note.follow_ups)),['First visit','Second visit']);
  assert.deepEqual(Array.from(helpers.fieldItems('')),[]);
});
test('summary preserves original fields, warnings and metadata with confidence caveat',()=>{
  const summary=helpers.noteSummary(note);
  for(const key of ['id','patient_id','diagnoses','medications','follow_ups','urgency','warning','created_at'])assert.ok(summary.includes(note[key]));
  assert.ok(summary.includes('82.34%'));assert.ok(summary.includes('not measured accuracy'));
});
test('image limits match backend MIME types and 5 MiB boundary',()=>{
  for(const type of ['image/png','image/jpeg','image/webp'])assert.equal(helpers.imageError({type,size:5*1024*1024}),'');
  for(const type of ['image/gif','image/svg+xml','application/pdf',''])assert.ok(helpers.imageError({type,size:20}));
  assert.ok(helpers.imageError({type:'image/png',size:0}));
  assert.ok(helpers.imageError({type:'image/png',size:5*1024*1024+1}));
});
function find(node,predicate){if(!node||typeof node!=='object')return; if(predicate(node))return node;return [node.props?.children].flat(Infinity).map(n=>find(n,predicate)).find(Boolean);}
for(const fail of [false,true])test(`clipboard ${fail?'failure':'success'} produces accessible feedback`,async()=>{
  const states=[];let cursor=0,copied;
  const jsx=(type,props)=>({type,props});
  const react={useState(initial){const i=cursor++;if(!(i in states))states[i]=initial;return [states[i],v=>states[i]=v];}};
  const {Result}=load('Result.tsx',{react,'react/jsx-runtime':{jsx,jsxs:jsx,Fragment:'fragment'},'lucide-react':{},'./notePresentation':helpers},{navigator:{clipboard:{writeText:async text=>{if(fail)throw Error('denied');copied=text;}}}});
  const render=()=>{cursor=0;return Result({note});};
  let tree=render();const click=find(tree,n=>n.type==='button').props.onClick;
  click();await new Promise(r=>setImmediate(r));tree=render();
  if(fail)assert.ok(find(tree,n=>n.props?.role==='alert'&&n.props.children.includes('Could not copy')));
  else{assert.equal(copied,helpers.noteSummary(note));assert.ok(find(tree,n=>n.props?.role==='status'&&n.props.children==='Summary copied.'));}
  assert.ok(find(tree,n=>n.type==='ul'));
});
test('upload preview cleans up object URLs and supports browse/drop with disabled guards',()=>{
  const states=[],effects=[];let cursor=0,cleanup,picked;
  const react={useState(initial){const i=cursor++;if(!(i in states))states[i]=initial;return [states[i],v=>states[i]=v];},useEffect(fn,deps){const i=cursor++;if(states[i]!==deps[0]){states[i]=deps[0];effects.push(fn);}}};
  const revoked=[];const jsx=(type,props)=>({type,props});
  const {ImageUpload}=load('ImageUpload.tsx',{react,'react/jsx-runtime':{jsx,jsxs:jsx},'lucide-react':{},'./notePresentation':helpers},{URL:{createObjectURL:()=> 'blob:preview',revokeObjectURL:url=>revoked.push(url)}});
  const file={name:'sample.png',type:'image/png',size:1234};
  const render=(disabled=false)=>{cursor=0;return ImageUpload({file,disabled,error:'',onPick:f=>picked=f,onRemove(){}});};
  let tree=render();for(const fn of effects.splice(0))cleanup=fn();tree=render();
  assert.equal(find(tree,n=>n.type==='img').props.src,'blob:preview');
  const input=find(tree,n=>n.type==='input');assert.equal(input.props.id,'note-image');
  assert.equal(input.props.accept,'image/png,image/jpeg,image/webp');
  const event={target:{files:[file],value:'sample.png'}};input.props.onChange(event);assert.equal(picked,file);assert.equal(event.target.value,'');
  picked=undefined;find(tree,n=>n.props?.onDrop).props.onDrop({preventDefault(){},dataTransfer:{files:[file]}});assert.equal(picked,file);
  picked=undefined;tree=render(true);assert.equal(find(tree,n=>n.type==='input').props.disabled,true);
  find(tree,n=>n.props?.onDrop).props.onDrop({preventDefault(){},dataTransfer:{files:[file]}});assert.equal(picked,undefined);
  cleanup();assert.deepEqual(revoked,['blob:preview']);
});
