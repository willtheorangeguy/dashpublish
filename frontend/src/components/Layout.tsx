import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import styles from './Layout.module.css'

const NAV_ITEMS = [
  { to: '/', label: 'Library', end: true },
  { to: '/build', label: 'Builder' },
  { to: '/status', label: 'Status' },
  { to: '/settings', label: 'Settings' },
]

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className={styles.shell}>
      <nav className={styles.nav}>
        <div className={styles.brand}>
          dash<span>publish</span>
        </div>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `${styles.link} ${isActive ? styles.linkActive : ''}`}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className={styles.main}>{children}</main>
    </div>
  )
}
