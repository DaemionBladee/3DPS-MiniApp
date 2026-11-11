import { useEffect, useState, type FormEvent } from 'react'
import { Button } from '../../components/ui/Button'
import type { DesignBrief, DesignFile, DesignScope } from './types'


export function BriefEditor({ brief, combined, disabled, paused, save, dirty }: { brief: DesignBrief; combined: boolean; disabled: boolean; paused: boolean; save: (brief: DesignBrief) => Promise<unknown>; dirty: (value: boolean) => void }) {
  const [value, setValue] = useState(brief)
  const signature = JSON.stringify(value), saved = JSON.stringify(brief)
  useEffect(() => {
    dirty(signature !== saved)
    if (signature === saved || disabled || paused) return
    const timer = setTimeout(() => { void save(JSON.parse(signature) as DesignBrief).catch(() => undefined) }, 650)
    return () => clearTimeout(timer)
  }, [signature, saved, disabled, paused, save, dirty])
  const change = (fields: Partial<DesignBrief>) => { dirty(true); setValue(previous => ({ ...previous, ...fields })) }
  return <fieldset className="print-form" disabled={disabled}><legend>Design brief</legend>
    <label htmlFor="design-description">Project description</label><textarea id="design-description" value={value.description} maxLength={4000} onChange={event => change({ description: event.target.value })} />
    <label htmlFor="design-use">Intended use</label><textarea id="design-use" value={value.intended_use} maxLength={2000} onChange={event => change({ intended_use: event.target.value })} />
    <label htmlFor="design-dimensions">Dimensions or size requirements</label><input id="design-dimensions" value={value.dimensions} maxLength={1000} onChange={event => change({ dimensions: event.target.value })} />
    <label htmlFor="design-units">Dimension units</label><select id="design-units" value={value.units} onChange={event => change({ units: event.target.value as DesignBrief['units'] })}><option value="mm">Millimeters</option><option value="cm">Centimeters</option><option value="inch">Inches</option><option value="not_sure">Not sure — Owner review</option></select>
    <label htmlFor="design-tolerances">Tolerances or precision needs</label><input id="design-tolerances" value={value.tolerances} maxLength={1000} placeholder="Not sure — please advise" onChange={event => change({ tolerances: event.target.value })} />
    <label htmlFor="design-manufacturing">Material or manufacturing preferences</label><textarea id="design-manufacturing" value={value.manufacturing_preferences} maxLength={1000} onChange={event => change({ manufacturing_preferences: event.target.value })} />
    <label htmlFor="design-date">Desired completion date</label><input type="date" id="design-date" value={value.desired_completion_date ?? ''} onChange={event => change({ desired_completion_date: event.target.value || null })} />
    <label htmlFor="design-special">Special requirements</label><textarea id="design-special" value={value.special_requirements} maxLength={2000} onChange={event => change({ special_requirements: event.target.value })} />
    <label htmlFor="design-delivery">Requested service deliverables</label><select id="design-delivery" value={value.delivery_kind} onChange={event => change({ delivery_kind: event.target.value as DesignBrief['delivery_kind'] })}>{!combined && <option value="digital">Digital design files (future authorized delivery)</option>}{combined && <><option value="printing">Manufacturing design + physical print; no digital source rights</option><option value="both">Digital design files and printing</option></>}</select>
    <p role="status">{signature === saved ? 'Design brief saved' : 'Draft autosave pending…'}</p>
  </fieldset>
}

export function DesignFilePicker({ disabled, purpose, onFile }: { disabled: boolean; purpose: 'design_reference' | 'design_proof' | 'design_manufacturing'; onFile: (file: File) => void }) {
  return <label className="print-file-picker">{purpose === 'design_reference' ? 'Choose a private reference' : purpose === 'design_proof' ? 'Choose a review proof' : 'Choose a private manufacturing model'}<input type="file" disabled={disabled} accept={purpose === 'design_manufacturing' ? '.stl,.3mf,.obj' : '.png,.jpg,.jpeg,.txt'} onChange={event => { const file = event.target.files?.[0]; if (file) onFile(file); event.target.value = '' }} /><span className="request-meta">{purpose === 'design_manufacturing' ? 'STL, Core 3MF or OBJ. Owner only; no digital release.' : 'PNG/JPEG images or plain UTF-8 TXT documents. No PDF, SVG or Office files.'}</span></label>
}

export function ScopeEditor({ combined, disabled, propose }: { combined: boolean; disabled: boolean; propose: (scope: DesignScope, reason: string) => void }) {
  const [value, setValue] = useState<DesignScope>({ deliverables: '', permitted_revisions: 1, exclusions: '', includes_digital_delivery: !combined })
  const [reason, setReason] = useState('')
  const submit = (event: FormEvent) => { event.preventDefault(); propose(value, reason) }
  return <form className="print-form" aria-label="Propose design scope" onSubmit={submit}><fieldset disabled={disabled} className="print-form"><legend>New scope proposal</legend>
    <label htmlFor="scope-deliverables">Agreed deliverables proposal</label><textarea id="scope-deliverables" required minLength={3} maxLength={3000} value={value.deliverables} onChange={event => setValue(previous => ({ ...previous, deliverables: event.target.value }))} />
    <label htmlFor="scope-revisions">Permitted revisions after first proof</label><input type="number" id="scope-revisions" min={0} max={20} required value={value.permitted_revisions} onChange={event => setValue(previous => ({ ...previous, permitted_revisions: Number(event.target.value) }))} />
    <label htmlFor="scope-exclusions">Exclusions</label><textarea id="scope-exclusions" maxLength={2000} value={value.exclusions} onChange={event => setValue(previous => ({ ...previous, exclusions: event.target.value }))} />
    <label className="print-checkbox"><input type="checkbox" disabled={!combined} checked={value.includes_digital_delivery} onChange={event => setValue(previous => ({ ...previous, includes_digital_delivery: event.target.checked }))} />Scope includes future digital-file delivery rights</label>
    <label htmlFor="scope-reason">Reason for scope proposal</label><input id="scope-reason" minLength={3} maxLength={500} required value={reason} onChange={event => setReason(event.target.value)} />
    <Button type="submit">Propose simulation scope</Button><p>Unapproved proposal. Customer agreement is required; no binding contract is issued in M05.</p>
  </fieldset></form>
}

export function PublishForm({ files, disabled, publish }: { files: DesignFile[]; disabled: boolean; publish: (preview: string, model: string | null, notes: string) => void }) {
  const [preview, setPreview] = useState(''), [model, setModel] = useState(''), [notes, setNotes] = useState('')
  return <form className="print-form" onSubmit={event => { event.preventDefault(); publish(preview, model || null, notes) }}><fieldset className="print-form" disabled={disabled}><legend>Publish immutable proof</legend>
    <label htmlFor="proof-preview">Review proof file</label><select id="proof-preview" required value={preview} onChange={event => setPreview(event.target.value)}><option value="">Choose an uploaded preview</option>{files.filter(file => file.purpose === 'design_proof').map(file => <option value={file.id} key={file.id}>{file.original_name}</option>)}</select>
    <label htmlFor="proof-manufacturing">Manufacturing-ready model (optional)</label><select id="proof-manufacturing" value={model} onChange={event => setModel(event.target.value)}><option value="">No manufacturing model yet</option>{files.filter(file => file.purpose === 'design_manufacturing').map(file => <option value={file.id} key={file.id}>{file.original_name}</option>)}</select>
    <label htmlFor="proof-notes">Proof release notes</label><textarea id="proof-notes" required minLength={3} maxLength={2000} value={notes} onChange={event => setNotes(event.target.value)} />
    <Button type="submit">Publish simulation proof</Button>
  </fieldset></form>
}
