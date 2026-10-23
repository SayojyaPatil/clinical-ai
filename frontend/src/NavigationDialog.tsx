import { useEffect, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';

export function NavigationDialog({children,onClose}:{children:ReactNode;onClose:()=>void}) {
  const dialog=useRef<HTMLDialogElement>(null);
  const close=useRef(onClose);close.current=onClose;
  useEffect(()=>{
    const element=dialog.current;
    const previous=document.activeElement as HTMLElement|null;
    element?.showModal();
    const desktop=window.matchMedia('(min-width: 1024px)');
    const resize=()=>{if(desktop.matches)close.current();};
    desktop.addEventListener('change',resize);
    return ()=>{desktop.removeEventListener('change',resize);element?.close();previous?.focus();};
  },[]);
  return <dialog ref={dialog} aria-label="Workspace navigation" onCancel={e=>{e.preventDefault();onClose();}} onClick={e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX>r.right||e.clientY>r.bottom)onClose();}}} className="fixed inset-y-0 left-0 m-0 h-dvh max-h-none w-[275px] max-w-[90vw] border-0 bg-[#f2f7f2] p-0 text-ink shadow-xl backdrop:bg-black/25"><div className="relative flex min-h-full flex-col">{children}<button type="button" autoFocus className="absolute right-3 top-3 rounded-lg p-2 text-[#638375]" onClick={onClose} aria-label="Close menu"><X size={18}/></button></div></dialog>;
}
