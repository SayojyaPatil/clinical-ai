import { useState } from 'react';
import { Copy, AlertCircle } from 'lucide-react';
import type { Note } from './api';
import { fieldItems, confidenceLabel, noteSummary } from './notePresentation';

export function Result({note,embedded=false}:{note:Note;embedded?:boolean}) {
  const [copyState,setCopyState]=useState('');
  async function copy(){setCopyState('busy');try{await navigator.clipboard.writeText(noteSummary(note));setCopyState('success');}catch{setCopyState('error');}}
  return <section aria-label={`Analysis results for ${note.patient_id}`} className={embedded?'border-t border-[#eaf0eb]':'surface overflow-hidden'}>
    <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-5 sm:px-7"><div className="min-w-0"><h2 className="heading text-base font-bold">Analysis results</h2>{!embedded&&<p className="mt-1 break-words text-xs text-[#647b6e]">{note.patient_id} · {new Date(note.created_at).toLocaleString()} · Urgency: {note.urgency}</p>}</div><button type="button" className="btn-ghost" disabled={copyState==='busy'} onClick={()=>void copy()}><Copy size={16}/>{copyState==='busy'?'Copying...':'Copy summary'}</button></div>
    <p className="mt-2 px-5 text-xs text-[#647b6e] [overflow-wrap:anywhere] sm:px-7">Analysis ID: {note.id}{embedded&&<> · Created: {new Date(note.created_at).toLocaleString()}</>}</p>
    <p role={copyState==='error'?'alert':'status'} className="px-5 text-xs text-pine-700 sm:px-7">{copyState==='success'?'Summary copied.':copyState==='error'?'Could not copy. Check clipboard permissions and try again.':''}</p>
    <div className="grid gap-3 p-5 sm:grid-cols-2 sm:p-7">{[{label:'DIAGNOSES',value:note.diagnoses},{label:'MEDICATIONS',value:note.medications},{label:'FOLLOW-UP',value:note.follow_ups}].map(item=>{const items=fieldItems(item.value);return <div key={item.label} className="min-w-0 rounded-xl border border-[#edf1ed] bg-[#f9fbf9] p-4"><h3 className="mb-3 text-[10px] font-bold tracking-wide text-[#647b6e]">{item.label}</h3>{items.length>1?<ul className="list-disc space-y-2 pl-5 text-[13px] leading-6 text-[#324a3d]">{items.map((text,i)=><li key={i} className="whitespace-pre-wrap [overflow-wrap:anywhere]">{text}</li>)}</ul>:<p className="whitespace-pre-wrap text-[13px] leading-6 text-[#324a3d] [overflow-wrap:anywhere]">{item.value||'Not specified'}</p>}</div>;})}<div className="rounded-xl border border-[#edf1ed] bg-[#f9fbf9] p-4"><h3 className="mb-3 text-[10px] font-bold tracking-wide text-[#647b6e]">SELF-REPORTED MODEL CONFIDENCE</h3><p className="text-lg font-semibold">{confidenceLabel(note.confidence)}</p><p className="mt-2 text-xs leading-5 text-[#647b6e]">The model’s own estimate, not measured accuracy or a calibrated probability.</p></div></div>
    <div className="mx-5 mb-5 flex gap-3 rounded-xl border border-[#e7e9df] bg-[#fbfbf4] px-4 py-3 text-[#756d48] sm:mx-7 sm:mb-7"><AlertCircle size={17} className="mt-0.5 shrink-0"/><p className="whitespace-pre-wrap text-xs leading-5 [overflow-wrap:anywhere]">{note.warning??'AI-generated extraction. Clinical review required before use.'}</p></div>
  </section>;
}
