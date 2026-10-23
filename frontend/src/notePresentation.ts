import type { Note } from './api';
// The API flattens extracted arrays with comma-space separators. Keep numeric
// commas (e.g. 1,000 mg) intact; copying always uses the original field text.
export const fieldItems = (value: string) => value.split(/\r?\n|[,;](?=\s|$)/).map(s=>s.trim()).filter(Boolean);
export const confidenceLabel = (value: number) => `${Number((value*100).toFixed(6))}%`;
export function noteSummary(n: Note): string {
  return [`Patient reference: ${n.patient_id}`,`Analysis ID: ${n.id}`,`Created: ${n.created_at}`,`Urgency: ${n.urgency}`,`Diagnoses:\n${n.diagnoses}`,`Medications:\n${n.medications}`,`Follow-up:\n${n.follow_ups}`,`Self-reported model confidence: ${confidenceLabel(n.confidence)} (not measured accuracy)`,`Warning: ${n.warning ?? 'AI-generated extraction. Clinical review required before use.'}`].join('\n\n');
}
export const IMAGE_TYPES = ['image/png','image/jpeg','image/webp'];
export function imageError(file: Pick<File,'type'|'size'>): string {
  if(!IMAGE_TYPES.includes(file.type))return 'Upload a PNG, JPG, or WebP image.';
  if(!file.size)return 'The image is empty. Choose another file.';
  if(file.size>5*1024*1024)return 'Image must be 5 MiB or smaller.';
  return '';
}
