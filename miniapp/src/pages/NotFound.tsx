import { Link } from 'react-router-dom'
import { Box } from 'lucide-react'

export default function NotFound() {
  return (
    <div className="standalone-state">
      <span className="brand-mark"><Box size={28} aria-hidden="true" /></span>
      <p className="eyebrow">PAGE NOT FOUND</p>
      <h1>This idea hasn’t taken shape.</h1>
      <p>The page you’re looking for is not part of this preview.</p>
      <Link className="button button--primary" to="/app">Back to workspace</Link>
    </div>
  )
}
