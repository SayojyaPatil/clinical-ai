import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, FileText, LoaderCircle, LockKeyhole, ZoomIn, ZoomOut } from 'lucide-react';
import { api, ApiError, type DocumentSource, type Note } from './api';
import { confidenceLabel, IMAGE_TYPES } from './notePresentation';

type ReviewData = {
  noteId: string; token: string; note: Note; source: DocumentSource;
  imageUrl: string; imageError: string;
};
type ReviewError = { noteId: string; token: string; message: string };

export function DocumentReview({ noteId, token, onUnauthorized, onBack }: {
  noteId: string; token: string; onUnauthorized: () => void; onBack: () => void;
}) {
  const [data, setData] = useState<ReviewData | null>(null);
  const [error, setError] = useState<ReviewError | null>(null);
  const [attempt, setAttempt] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let objectUrl = '';
    let unauthorized = false;
    const guarded = async <T,>(operation: Promise<T>): Promise<T> => {
      try { return await operation; }
      catch (err) {
        if (active && err instanceof ApiError && err.status === 401) {
          if (!unauthorized) { unauthorized = true; setData(null); onUnauthorized(); }
          controller.abort();
        }
        throw err;
      }
    };
    setData(null); setError(null);
    async function load() {
      try {
        const [note, source] = await Promise.all([
          guarded(api.note(token, noteId, controller.signal)),
          guarded(api.source(token, noteId, controller.signal)),
        ]);
        if (!active || unauthorized) return;
        let imageError = '';
        if (source.kind === 'image' && source.availability === 'available') {
          try {
            const blob = await guarded(api.sourceContent(token, noteId, controller.signal));
            if (!active || unauthorized) return;
            if (!IMAGE_TYPES.includes(blob.type)) throw new Error('The server returned an unsupported image format.');
            objectUrl = URL.createObjectURL(blob);
          } catch (err) {
            if (!active || unauthorized) return;
            imageError = err instanceof ApiError && err.status === 404
              ? 'Original image unavailable. The stored image could not be retrieved.'
              : 'Could not load the original image. Please try again.';
          }
        }
        if (active) setData({ noteId, token, note, source, imageUrl: objectUrl, imageError });
      } catch (err) {
        if (!active || unauthorized) return;
        controller.abort();
        setError({ noteId, token, message: err instanceof ApiError && err.status === 404
          ? 'This analysis is unavailable or you do not have access to it.'
          : 'Could not load this document. Please try again.' });
      }
    }
    void load();
    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [noteId, token, attempt, onUnauthorized]);

  // Never render a previous document/account while a new effect is starting.
  const current = data?.noteId === noteId && data.token === token ? data : null;
  const currentError = error?.noteId === noteId && error.token === token ? error : null;
  const retry = () => { setData(null); setError(null); setAttempt(value => value + 1); };
  return <div>
    <button type="button" className="btn-ghost mb-4" onClick={onBack}><ArrowLeft size={16}/>Back to analysis history</button>
    <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0"><h1 ref={heading} tabIndex={-1} className="heading text-[30px] font-extrabold text-[#183d31] sm:text-[36px]">Document review<span className="text-pine-600">.</span></h1>
        <p className="mt-2 text-sm text-[#647b6e]">Compare the original source with the immutable AI extraction.</p>
        {current && <p className="mt-2 break-words text-sm font-semibold text-pine-800">{current.note.patient_id}</p>}
      </div>
      {current && <span className="rounded-full border border-[#d5e4d8] bg-pine-50 px-3 py-2 text-xs font-bold text-pine-800">{current.source.review_status ? current.source.review_status.charAt(0).toUpperCase() + current.source.review_status.slice(1) : 'Review status unavailable'}</span>}
    </div>
    {currentError ? <div role="alert" className="surface p-6 text-sm text-rose-700"><p>{currentError.message}</p><button type="button" className="btn-ghost mt-3" onClick={retry}>Retry document loading</button></div>
      : !current ? <div role="status" className="surface flex items-center justify-center gap-3 p-12 text-sm text-pine-700"><LoaderCircle size={20} className="animate-spin"/>Loading original document and AI extraction...</div>
      : <>
        <p className="mb-5 rounded-xl border border-[#e2ebe4] bg-white p-4 text-xs leading-5 text-[#647b6e]">Read-only document view. Human corrections and approval are not available yet; no review decision is recorded by opening this screen.</p>
        <div className="grid items-start gap-6 xl:grid-cols-2">
          <section aria-labelledby="original-source-heading" className="surface min-w-0 overflow-hidden">
            <div className="border-b border-[#eaf0eb] p-5"><h2 id="original-source-heading" className="heading flex items-center gap-2 text-base font-bold"><FileText size={18}/>Original source</h2><p className="mt-2 text-xs text-[#647b6e]">{current.source.provenance === 'legacy_inferred' ? 'Legacy source provenance inferred from stored records.' : 'Preserved submission · Read-only'}</p></div>
            <div className="p-5">
              {current.source.availability === 'unavailable' ? <div role="status" className="rounded-xl bg-[#f9fbf9] p-5 text-sm leading-6 text-[#647b6e]"><h3 className="mb-2 font-bold text-[#324a3d]">Original source unavailable</h3><p>{current.source.unavailable_reason ?? 'No original document is available for this record.'}</p><p className="mt-2">The stored AI output remains available alongside this notice.</p></div>
                : current.source.kind === 'text' && current.source.original_text !== null ? <pre tabIndex={0} aria-label="Original submitted text" className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-xl border border-[#e4ebe6] bg-[#fafcf9] p-4 font-sans text-sm leading-7 text-[#324a3d] [overflow-wrap:anywhere]">{current.source.original_text}</pre>
                : current.source.kind === 'image' ? current.imageError ? <div role="alert" className="text-sm leading-6 text-rose-700"><p>{current.imageError}</p><button type="button" className="btn-ghost mt-3" onClick={retry}>Retry image loading</button></div>
                  : <ImageSourcePreview key={current.imageUrl} source={current.source} url={current.imageUrl} patient={current.note.patient_id}/>
                : <p role="status" className="text-sm text-[#647b6e]">Original source unavailable. No previewable source was retained.</p>}
              {current.source.kind === 'text' && current.source.availability === 'available' && <SourceDetails source={current.source}/>}
            </div>
          </section>
          <OriginalExtraction note={current.note} source={current.source}/>
        </div>
      </>}
  </div>;
}

function SourceDetails({ source, dimensions }: { source: DocumentSource; dimensions?: string }) {
  return <details className="mt-4 text-xs text-[#647b6e]"><summary className="cursor-pointer rounded-lg py-2 font-bold text-pine-800">{source.kind === 'image' ? 'Image details' : 'Source details'}</summary>
    <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 rounded-xl bg-[#f9fbf9] p-3">
      {Object.entries({Filename: source.original_filename ?? 'Not recorded', Type: source.mime_type ?? 'Not recorded', Size: source.byte_size !== null ? `${source.byte_size.toLocaleString()} bytes` : 'Not recorded', ...(dimensions ? {Dimensions: dimensions} : {}), 'SHA-256': source.sha256 ?? 'Not recorded', 'Stored at': source.stored_at ?? 'Not recorded'}).map(([label,value])=><div key={label} className="contents"><dt className="font-semibold">{label}</dt><dd className="whitespace-pre-wrap [overflow-wrap:anywhere]">{value}</dd></div>)}
    </dl>
  </details>;
}

export function ImageSourcePreview({ source, url, patient }: { source: DocumentSource; url: string; patient: string }) {
  const [zoom,setZoom] = useState(100);
  const [dimensions,setDimensions] = useState('');
  const [failed,setFailed] = useState(false);
  return <div>
    <p className="mb-3 break-words text-sm font-semibold text-[#324a3d]">{source.original_filename ?? 'Original image'}</p>
    <div className="mb-3 flex flex-wrap items-center gap-2" role="group" aria-label="Image zoom controls">
      <button type="button" className="btn-ghost" aria-label="Zoom out" disabled={zoom <= 100} onClick={()=>setZoom(value=>Math.max(100,value-25))}><ZoomOut size={16}/></button>
      <output aria-live="polite" aria-label="Image zoom" className="min-w-12 text-center text-xs text-pine-800">{zoom}%</output>
      <button type="button" className="btn-ghost" aria-label="Zoom in" disabled={zoom >= 400} onClick={()=>setZoom(value=>Math.min(400,value+25))}><ZoomIn size={16}/></button>
      <button type="button" className="btn-ghost" onClick={()=>setZoom(100)}>Fit image</button>
    </div>
    {failed ? <p role="alert" className="text-sm text-rose-700">This browser could not display the stored image. Its metadata remains available below.</p>
      : <div tabIndex={0} role="region" aria-label="Original image preview; scroll to inspect when zoomed" className="max-h-[70vh] overflow-auto rounded-xl border border-[#e4ebe6] bg-[#f2f7f2]">
        <img src={url} alt={`Original clinical note for ${patient}`} className="block h-auto max-w-none" style={{width:`${zoom}%`}} onLoad={e=>setDimensions(`${e.currentTarget.naturalWidth} × ${e.currentTarget.naturalHeight} pixels`)} onError={()=>setFailed(true)}/>
      </div>}
    <SourceDetails source={source} dimensions={dimensions}/>
  </div>;
}

function OriginalExtraction({ note, source }: { note: Note; source: DocumentSource }) {
  const extraction = source.ai_result;
  return <section aria-labelledby="original-ai-heading" className="surface min-w-0 overflow-hidden">
    <div className="border-b border-[#eaf0eb] p-5"><h2 id="original-ai-heading" className="heading flex items-center gap-2 text-base font-bold"><LockKeyhole size={18}/>Original AI output</h2><p className="mt-2 text-xs text-[#647b6e]">Immutable AI extraction. No human corrections are shown in this stage.</p></div>
    <div className="space-y-4 p-5">
      {!extraction && <p className="rounded-xl bg-[#f9fbf9] p-3 text-xs leading-5 text-[#647b6e]">Legacy extraction: structured lists were not retained. Stored field text is shown unchanged.</p>}
      {(['diagnoses','medications','follow_ups'] as const).map(field=><div key={field} className="rounded-xl border border-[#edf1ed] bg-[#f9fbf9] p-4"><h3 className="mb-2 text-xs font-bold text-[#516c5c]">{field === 'follow_ups' ? 'Follow-up' : field.charAt(0).toUpperCase()+field.slice(1)}</h3>
        {extraction ? extraction[field].length ? <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-[#324a3d]">{extraction[field].map((item,index)=><li key={index} className="whitespace-pre-wrap [overflow-wrap:anywhere]">{item}</li>)}</ul> : <p className="text-sm text-[#647b6e]">No items extracted.</p>
          : <p className="whitespace-pre-wrap text-sm leading-6 text-[#324a3d] [overflow-wrap:anywhere]">{note[field] || 'No information extracted.'}</p>}
      </div>)}
      <dl className="space-y-3 text-sm text-[#324a3d]"><div><dt className="text-xs font-bold text-[#516c5c]">AI urgency label</dt><dd className="mt-1">{extraction?.urgency ?? note.urgency}</dd></div><div><dt className="text-xs font-bold text-[#516c5c]">Self-reported model confidence</dt><dd className="mt-1">{confidenceLabel(extraction?.confidence ?? note.confidence)}<p className="mt-1 text-xs leading-5 text-[#647b6e]">The model’s estimate, not measured accuracy or a calibrated probability.</p></dd></div><div><dt className="text-xs font-bold text-[#516c5c]">Analysis ID</dt><dd className="mt-1 break-all">{note.id}</dd></div><div><dt className="text-xs font-bold text-[#516c5c]">Created at</dt><dd className="mt-1 break-words">{note.created_at}</dd></div><div><dt className="text-xs font-bold text-[#516c5c]">Model</dt><dd className="mt-1">{source.model_name ?? 'Not recorded'}</dd></div></dl>
      <p className="whitespace-pre-wrap rounded-xl border border-[#e7e9df] bg-[#fbfbf4] p-4 text-xs leading-5 text-[#756d48] [overflow-wrap:anywhere]">{note.warning ?? 'AI-generated extraction. Clinical review required before use.'}</p>
    </div>
  </section>;
}
