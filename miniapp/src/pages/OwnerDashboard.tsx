import { ClipboardCheck, CreditCard, Layers3, PackageOpen, ShieldCheck, Wrench } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/States'

const modules = [
  { title: 'Reviews', description: 'A place to review requests, clarify scope, and approve special requirements.', Icon: ClipboardCheck },
  { title: 'Payments', description: 'A place for stage-specific payment review and verified settlement records.', Icon: CreditCard },
  { title: 'Production', description: 'A place for approved assignments, production attempts, and quality checks.', Icon: Wrench },
  { title: 'Inventory', description: 'A place for material variants, spool movements, and reservations.', Icon: Layers3 },
]

export default function OwnerDashboard() {
  return (
    <div className="dashboard">
      <section className="welcome-row" aria-labelledby="owner-title">
        <div><p className="eyebrow">THE WORKSHOP AT A GLANCE</p><h1 id="owner-title">Your workshop, at a glance<span className="accent-text">.</span></h1><p className="page-description">One workspace for a thoughtful operation.</p></div>
        <Badge tone="accent"><span className="status-dot" />Prelaunch preview</Badge>
      </section>
      <section className="owner-intro" aria-labelledby="owner-intro-title">
        <span className="owner-intro-icon"><ShieldCheck size={27} aria-hidden="true" /></span>
        <div><p className="eyebrow">A FOUNDATION, READY TO GROW</p><h2 id="owner-intro-title">Your workshop starts here.</h2><p>This is a workspace preview. Reviews, payment verification, production, and stock records are not connected yet.</p></div>
        <Badge>Live operations disabled</Badge>
      </section>
      <section className="dashboard-section" aria-labelledby="modules-title">
        <div className="section-heading"><div><p className="eyebrow">YOUR DAILY WORKSPACE</p><h2 id="modules-title">Everything in its place.</h2></div><span className="section-note">Tools coming in later releases</span></div>
        <div className="owner-module-grid">
          {modules.map(({ title, description, Icon }) => (
            <Card className="owner-module" key={title} aria-label={title}>
              <div className="module-top"><span className="service-icon"><Icon size={24} strokeWidth={1.6} aria-hidden="true" /></span><Badge>Not connected</Badge></div>
              <h3>{title}</h3><p>{description}</p><div className="module-footer">Available in a later release</div>
            </Card>
          ))}
        </div>
      </section>
      <Card className="owner-activity" aria-labelledby="activity-title">
        <div className="section-heading"><h2 id="activity-title">Workshop activity</h2><PackageOpen size={19} className="muted-icon" aria-hidden="true" /></div>
        <EmptyState icon={ClipboardCheck} title="A clear starting point" description="There are no connected operational records in this preview. Future updates will reflect verified project events." />
      </Card>
      <p className="owner-safety-note"><ShieldCheck size={16} aria-hidden="true" />This preview does not grant access to customer data or authorize business actions.</p>
    </div>
  )
}
