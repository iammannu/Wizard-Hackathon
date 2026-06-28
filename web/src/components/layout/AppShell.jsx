import React from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  MessageSquare, SlidersHorizontal, BarChart2,
  Briefcase, Calendar, Zap, Home,
} from 'lucide-react'
import styles from './AppShell.module.css'

const NAV = [
  { to: '/app/workspaces', icon: Zap,                label: 'Workspaces',  badge: 'NEW' },
  { to: '/app/research',   icon: MessageSquare,       label: 'Research' },
  { to: '/app/screener',   icon: SlidersHorizontal,   label: 'Screener' },
  { to: '/app/market',     icon: BarChart2,            label: 'Market' },
  { to: '/app/portfolio',  icon: Briefcase,            label: 'Portfolio' },
  { to: '/app/events',     icon: Calendar,             label: 'Events' },
]

export default function AppShell() {
  const navigate = useNavigate()
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.logo} onClick={() => navigate('/')}>
          <div className={styles.logoMark}>α</div>
          <div>
            <div className={styles.logoText}>AlphaForage</div>
            <div className={styles.logoSub}>AUTONOMOUS INTELLIGENCE</div>
          </div>
        </div>

        <nav className={styles.nav}>
          <div className={styles.navSection}>Platform</div>
          {NAV.slice(0, 1).map(({ to, icon: Icon, label, badge }) => (
            <NavLink
              key={to} to={to}
              className={({ isActive }) => `${styles.navItem} ${isActive ? styles.active : ''}`}
            >
              <Icon size={15} />
              <span style={{ flex: 1 }}>{label}</span>
              {badge && <span style={{ fontSize: '8px', padding: '1px 5px', borderRadius: '3px', background: 'rgba(108,92,231,0.2)', color: 'var(--accent2)', border: '1px solid rgba(108,92,231,0.3)', fontWeight: 700, letterSpacing: '0.5px' }}>{badge}</span>}
            </NavLink>
          ))}

          <div className={styles.navSection}>Research</div>
          {NAV.slice(1, 4).map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to} to={to}
              className={({ isActive }) => `${styles.navItem} ${isActive ? styles.active : ''}`}
            >
              <Icon size={15} />
              <span>{label}</span>
            </NavLink>
          ))}

          <div className={styles.navSection}>Portfolio</div>
          {NAV.slice(4).map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to} to={to}
              className={({ isActive }) => `${styles.navItem} ${isActive ? styles.active : ''}`}
            >
              <Icon size={15} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className={styles.sidebarBottom}>
          <div style={{ fontSize: '10px', color: 'var(--muted)', marginBottom: '6px', lineHeight: 1.5 }}>
            <div style={{ color: 'var(--accent2)', fontWeight: 600, marginBottom: '2px' }}>Research Engines</div>
            <div>You.com · Tavily</div>
          </div>
          <div className={styles.statusRow}>
            <span className={styles.statusDot} />
            <span className={styles.statusText}>12 Agents · :8000</span>
          </div>
        </div>
      </aside>

      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}
