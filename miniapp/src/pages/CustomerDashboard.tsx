import { useAuth } from '../features/auth/context'
import { RequestWorkspace } from '../features/requests/RequestWorkspace'
import { ArrowRight, Box, Cuboid, Layers3, PackageOpen, PenTool, ShieldCheck, Sparkles } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/States'

const services = [
  { title: '3D printing', eyebrow: 'FROM FILE TO FINISHED', description: 'Have a model ready? Turn your existing 3D files into something you can hold.', Icon: Cuboid, detail: 'STL · 3MF · OBJ' },
  { title: 'Custom design', eyebrow: 'START WITH AN IDEA', description: 'Bring a sketch, a reference, or a problem. Shape it into a considered 3D design.', Icon: PenTool, detail: 'Brief · Design · Review' },
  { title: 'Design + print', eyebrow: 'THE COMPLETE JOURNEY', description: 'Take an idea from the first sketch through design approval to a physical print.', Icon: Layers3, detail: 'Two stages, one project' },
]

export default function CustomerDashboard() {
  const { session } = useAuth()
  return (
    <div className="dashboard">
      <section className="welcome-row" aria-labelledby="customer-title">
        <div><p className="eyebrow">YOUR IDEAS START HERE</p><h1 id="customer-title">Your next idea, made real<span className="accent-text">.</span></h1><p className="page-description">A little imagination. A new dimension.</p></div>
        <Badge tone="accent"><span className="status-dot" />Prelaunch preview</Badge>
      </section>

      <section className="hero-panel" aria-labelledby="hero-title">
        <div className="hero-copy">
          <span className="hero-kicker"><Sparkles size={15} aria-hidden="true" />BUILT FOR WHAT’S NEXT</span>
          <h2 id="hero-title">From possibility<br />to something real.</h2>
          <p>{session ? "Save a simulation project draft and add your ideas for printing or custom design." : "Explore a simpler home for 3D printing and custom design. Your next project will begin here."}</p>
          <Button disabled={!session} aria-describedby="request-later" onClick={() => document.getElementById('projects-title')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{session ? 'View project drafts' : 'Start a project'}<ArrowRight size={17} aria-hidden="true" /></Button>
          <span id="request-later" className="hero-note">{session ? "Save a draft below. File intake and submission open in a later release." : "Project requests are coming in a later release."}</span>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="art-grid" />
          <span className="art-label art-label--top">IDEA / FORM / OBJECT</span>
          <div className="object-orbit orbit-one" /><div className="object-orbit orbit-two" />
          <div className="sculpture"><div className="sculpture-layer layer-one" /><div className="sculpture-layer layer-two" /><div className="sculpture-layer layer-three" /><div className="sculpture-layer layer-four" /><div className="sculpture-layer layer-five" /></div>
          <span className="art-label art-label--bottom"><span />A NEW DIMENSION</span>
        </div>
      </section>

      <section aria-labelledby="services-title" className="dashboard-section">
        <div className="section-heading"><div><p className="eyebrow">THREE WAYS TO CREATE</p><h2 id="services-title">What will you make?</h2></div><span className="section-note">Services coming soon</span></div>
        <div className="service-grid">
          {services.map(({ title, eyebrow, description, Icon, detail }) => (
            <Card key={title} className="service-card" aria-label={title}>
              <span className="service-icon"><Icon size={23} strokeWidth={1.6} aria-hidden="true" /></span>
              <p className="service-eyebrow">{eyebrow}</p><h3>{title}</h3><p className="service-description">{description}</p>
              <div className="service-footer"><span>{detail}</span><Badge>Coming later</Badge></div>
            </Card>
          ))}
        </div>
      </section>

      <div className="customer-bottom-grid">
        <Card className="projects-card" aria-labelledby="projects-title">
          <div className="section-heading"><h2 id="projects-title">Your projects</h2><PackageOpen size={19} className="muted-icon" aria-hidden="true" /></div>
          {session ? <RequestWorkspace /> : <EmptyState icon={Box} title="A fresh canvas" description="Your projects will have a home here once requests are available. There are no connected project records in this preview." />}
        </Card>
        <Card className="process-card" aria-labelledby="process-title">
          <p className="eyebrow">CLEAR AT EVERY STEP</p><h2 id="process-title">A considered process.</h2>
          <ol className="process-list"><li><span>01</span><div><h3>Tell us what you need</h3><p>A model, a brief, or an idea to explore.</p></div></li><li><span>02</span><div><h3>Review the details</h3><p>Agree the scope before a stage begins.</p></div></li><li><span>03</span><div><h3>Follow your project</h3><p>Clear updates from design to handoff.</p></div></li></ol>
          <p className="process-footnote"><ShieldCheck size={16} aria-hidden="true" />No live orders or payments in this preview.</p>
        </Card>
      </div>
    </div>
  )
}
