import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Landing } from './pages/Landing.jsx'
import { Market, Portfolio, Events } from './pages/pages.jsx'
import AppShell from './components/layout/AppShell.jsx'
import Research from './pages/Research.jsx'
import Screener from './pages/Screener.jsx'
import Workspaces from './pages/Workspaces.jsx'
import WorkspaceDetail from './pages/WorkspaceDetail.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/app" element={<AppShell />}>
        <Route index element={<Navigate to="/app/workspaces" replace />} />
        <Route path="workspaces"     element={<Workspaces />} />
        <Route path="workspaces/:id" element={<WorkspaceDetail />} />
        <Route path="research"       element={<Research />} />
        <Route path="screener"       element={<Screener />} />
        <Route path="market"         element={<Market />} />
        <Route path="portfolio"      element={<Portfolio />} />
        <Route path="events"         element={<Events />} />
      </Route>
    </Routes>
  )
}
