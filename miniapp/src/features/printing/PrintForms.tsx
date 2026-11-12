import { useEffect, useState } from 'react'
import { Button } from '../../components/ui/Button'
import type { ItemDetail, ItemSpecification, PrintingOptions } from './types'

export function ItemEditor({ item, catalog, disabled, paused, save, markDirty, clearError }: {
  item: ItemDetail; catalog: PrintingOptions; disabled: boolean; paused: boolean;
  save: (id: string, spec: ItemSpecification) => Promise<unknown>; markDirty: (id: string, value: boolean) => void; clearError: () => void
}) {
  const [spec, setSpec] = useState(item.specification)
  const signature = JSON.stringify(spec)
  const serverSignature = JSON.stringify(item.specification)
  const dimensions = [spec.dimension_x_mm, spec.dimension_y_mm, spec.dimension_z_mm]
  const dimensionsValid = dimensions.every(v => v == null) || dimensions.every(v => typeof v === 'number' && Number.isFinite(v) && v > 0 && v <= 1000000)
  const valid = dimensionsValid && Number.isInteger(spec.quantity) && (spec.quantity ?? 0) >= 1 && (spec.quantity ?? 0) <= 1000
  useEffect(() => {
    markDirty(item.id, signature !== serverSignature)
    if (signature === serverSignature || !valid || disabled || paused) return
    const timer = setTimeout(() => { void save(item.id, JSON.parse(signature) as ItemSpecification).catch(() => undefined) }, 600)
    return () => clearTimeout(timer)
  }, [signature, serverSignature, valid, disabled, paused, save, markDirty, item.id])
  const change = (value: Partial<ItemSpecification>) => { markDirty(item.id, true); clearError(); setSpec(previous => ({ ...previous, ...value })) }
  const material = catalog.materials.find(option => option.key === spec.material_key)
  return <fieldset disabled={disabled} className="print-form"><legend>Printing settings</legend>
    <label htmlFor={`description-${item.id}`}>Item description</label><input id={`description-${item.id}`} maxLength={300} value={spec.description ?? ''} onChange={event => change({ description: event.target.value })} />
    <label htmlFor={`quantity-${item.id}`}>Quantity</label><input id={`quantity-${item.id}`} type="number" min={1} max={1000} required value={spec.quantity ?? 1} onChange={event => change({ quantity: Number(event.target.value) })} />
    {!valid && <p role="alert">Quantity must be between 1 and 1000.</p>}
    <label htmlFor={`material-${item.id}`}>Material</label><select id={`material-${item.id}`} value={spec.material_key ?? ''} onChange={event => change({ material_key: event.target.value ? event.target.value as NonNullable<ItemSpecification['material_key']> : null, color_key: null })}>
      <option value="">Choose a development option</option>{catalog.materials.map(option => <option key={option.key} value={option.key}>{option.label}</option>)}
    </select>
    <label htmlFor={`color-${item.id}`}>Color</label><select id={`color-${item.id}`} value={spec.color_key ?? ''} onChange={event => change({ color_key: event.target.value ? event.target.value as NonNullable<ItemSpecification['color_key']> : null })}>
      <option value="">Choose a development color</option>{catalog.colors.filter(option => material?.color_keys.includes(option.key)).map(option => <option key={option.key} value={option.key}>{option.label}</option>)}
    </select>
    <label htmlFor={`quality-${item.id}`}>Quality</label><select id={`quality-${item.id}`} value={spec.quality_key ?? ''} onChange={event => change({ quality_key: event.target.value ? event.target.value as NonNullable<ItemSpecification['quality_key']> : null })}>
      <option value="">Choose a development quality</option>{catalog.qualities.map(option => <option key={option.key} value={option.key}>{option.label}</option>)}
    </select>
    <label htmlFor={`units-${item.id}`}>Model units</label><select id={`units-${item.id}`} value={spec.unit_key ?? 'mm'} onChange={event => change({ unit_key: event.target.value as ItemSpecification['unit_key'], unit_confirmed: false })}>
      {catalog.units.map(option => <option key={option.key} value={option.key}>{option.label}</option>)}
    </select>
    <label className="print-checkbox"><input type="checkbox" checked={spec.unit_confirmed ?? false} onChange={event => change({ unit_confirmed: event.target.checked })} />I confirm these are the model’s intended units</label>
    <p>Optional target dimensions in millimeters. Complete all three to check the calculated model scale.</p>
    {(['x', 'y', 'z'] as const).map(axis => <div key={axis}><label htmlFor={`dimension-${axis}-${item.id}`}>Target {axis.toUpperCase()} (mm)</label><input id={`dimension-${axis}-${item.id}`} type="number" min={0.001} max={1000000} step="any" value={spec[`dimension_${axis}_mm`] ?? ''} onChange={event => change({ [`dimension_${axis}_mm`]: event.target.value === '' ? null : Number(event.target.value) })} /></div>)}
    {!dimensionsValid && <p role="alert">Enter three positive target dimensions, or leave all three blank.</p>}
    <label htmlFor={`special-${item.id}`}>Special requirements</label><textarea id={`special-${item.id}`} maxLength={2000} value={spec.special_requirements ?? ''} onChange={event => change({ special_requirements: event.target.value })} />
    <p className="request-meta" role="status">{signature === serverSignature ? 'Settings saved' : 'Unsaved settings — autosave pending'}</p>
  </fieldset>
}

export function PreferencesEditor({ notes, method, fulfillmentNotes, disabled, paused, save, markDirty, clearError }: {
  notes: string; method: 'pickup' | 'delivery'; fulfillmentNotes: string; disabled: boolean; paused: boolean;
  save: (notes: string, method: 'pickup' | 'delivery', fulfillmentNotes: string) => Promise<unknown>; markDirty: (id: string, value: boolean) => void; clearError: () => void
}) {
  const [values, setValues] = useState({ notes, method, fulfillmentNotes })
  const signature = JSON.stringify(values)
  const savedSignature = JSON.stringify({ notes, method, fulfillmentNotes })
  useEffect(() => {
    markDirty('preferences', signature !== savedSignature)
    if (signature === savedSignature || disabled || paused) return
    const timer = setTimeout(() => { const value = JSON.parse(signature) as typeof values; void save(value.notes, value.method, value.fulfillmentNotes).catch(() => undefined) }, 600)
    return () => clearTimeout(timer)
  }, [signature, savedSignature, disabled, paused, save, markDirty])
  return <fieldset disabled={disabled} className="print-form"><legend>Project and fulfillment preferences</legend>
    <label htmlFor="print-project-notes">Project notes</label><textarea id="print-project-notes" maxLength={2000} value={values.notes} onChange={event => { markDirty('preferences', true); clearError(); setValues(previous => ({ ...previous, notes: event.target.value })) }} />
    <label htmlFor="print-fulfillment">Preferred handoff</label><select id="print-fulfillment" value={values.method} onChange={event => { markDirty('preferences', true); clearError(); setValues(previous => ({ ...previous, method: event.target.value as typeof method })) }}><option value="pickup">Pickup preference</option><option value="delivery">Delivery preference</option></select>
    <label htmlFor="print-fulfillment-notes">Fulfillment notes (optional)</label><textarea id="print-fulfillment-notes" maxLength={1000} value={values.fulfillmentNotes} onChange={event => { markDirty('preferences', true); clearError(); setValues(previous => ({ ...previous, fulfillmentNotes: event.target.value })) }} />
    <p className="request-meta" role="status">{signature === savedSignature ? 'Preferences saved' : 'Saving preferences…'}</p>
  </fieldset>
}

export function FilePicker({ onFiles, disabled, multiple = true, label = 'Choose model files' }: { onFiles: (files: File[]) => void; disabled: boolean; multiple?: boolean; label?: string }) {
  return <label className="print-file-picker">{label}<input type="file" accept=".stl,.3mf,.obj" multiple={multiple} disabled={disabled} onChange={event => { onFiles(Array.from(event.target.files ?? [])); event.target.value = '' }} /></label>
}

export function DownloadButton({ download, disabled = false }: { download: () => void; disabled?: boolean }) {
  return <Button variant="secondary" disabled={disabled} onClick={download}>Download private model</Button>
}
