import { intakeData, CUSTOMER_ID, FILE_ID, REQUEST_ID } from '../printing/test-fixtures'
import type { DesignDetail, DesignFile } from './types'
export const DESIGN_ID = '00000000-0000-4000-8000-000000000050'
export const SCOPE_ID = '00000000-0000-4000-8000-000000000060'
export const VERSION_ID = '00000000-0000-4000-8000-000000000070'
export function fileData(purpose: DesignFile['purpose'] = 'design_proof'): DesignFile {
  return { id: FILE_ID, request_id: REQUEST_ID, request_item_id: null, request_revision: 2, purpose, original_name: 'proof.txt', size_bytes: 20, sha256: 'a'.repeat(64), format: 'txt', format_details: {}, validation_status: 'validated', storage_state: 'ready', download_allowed: true, failure_code: null }
}
export function designData(): DesignDetail {
  return { id: DESIGN_ID, request: { ...intakeData().request, id: REQUEST_ID, customer_id: CUSTOMER_ID, stage_kind: 'design', service_type: 'custom_design' }, state: 'draft', brief: { description: 'A desk bracket', intended_use: 'Indoor testing', dimensions: '30 x 20 x 10', units: 'mm', tolerances: 'Not sure', manufacturing_preferences: '', desired_completion_date: null, special_requirements: '', delivery_kind: 'digital' }, scopes: [], approved_scope_id: null, versions: [], latest_version_id: null, approved_version_id: null, references: [], working_files: [], simulation_fixture: false, linked_print_request: null, linked_print_item_id: null, customer_display_name: 'Test Customer', digital_release_available: false, notice: 'Simulation only. No quotation, payment, live work or digital release.' }
}
export function proofData(): DesignDetail {
  const data = designData()
  data.request.status = 'submitted'; data.state = 'customer_review'; data.latest_version_id = VERSION_ID
  data.approved_scope_id = SCOPE_ID; data.simulation_fixture = true
  data.scopes = [{ id: SCOPE_ID, number: 1, scope: { deliverables: 'Preview and model', permitted_revisions: 2, exclusions: '', includes_digital_delivery: true }, agreed: true, binding: false }]
  data.versions = [{ id: VERSION_ID, number: 2, scope_id: SCOPE_ID, preview: fileData(), manufacturing_file: null, manufacturing_ready: false, release_notes: 'New current proof', specification_sha256: 'b'.repeat(64), review: null }]
  return data
}
