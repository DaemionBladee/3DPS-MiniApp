import { useEffect, useState } from 'react'
import { Button } from '../../components/ui/Button'
import { apiPrivateBlob } from '../../lib/api/client'
import type { DesignFile } from './types'

export function ProofViewer({ file }: { file: DesignFile }) {
  const [opened, setOpened] = useState(false)
  const [url, setUrl] = useState<string | null>(null), [content, setContent] = useState<string | null>(null), [error, setError] = useState(false)
  useEffect(() => {
    if (!opened) return
    const controller = { active: true, url: '' }
    void apiPrivateBlob(`/files/${file.id}/download`).then(async blob => {
      if (!controller.active) return
      if (file.format === 'txt') { const text = await blob.text(); if (controller.active) setContent(text) }
      else if (file.format === 'png' || file.format === 'jpeg') {
        controller.url = URL.createObjectURL(new Blob([blob], { type: `image/${file.format}` })); setUrl(controller.url)
      } else setError(true)
    }).catch(() => { if (controller.active) setError(true) })
    return () => { controller.active = false; if (controller.url) URL.revokeObjectURL(controller.url) }
  }, [file.id, file.format, opened])
  return <div className="design-proof-viewer">{!opened ? <Button variant="secondary" onClick={() => setOpened(true)}>View proof {file.original_name}</Button> : error ? <p role="alert">This private proof could not be loaded. Check your session and reopen the request.</p> : url ? <img className="design-proof-image" src={url} alt={`Design proof: ${file.original_name}`} /> : content !== null ? <pre className="design-proof-text">{content}</pre> : <p role="status">Loading private proof…</p>}</div>
}
