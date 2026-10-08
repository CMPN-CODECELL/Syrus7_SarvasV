import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { username: 'tester', account_id: 'acc_tester' }, logout: vi.fn() }) }))
vi.mock('../telemetry/TelemetryContext', () => ({ useTelemetry: () => ({ snapshot: {}, status: 'live', refresh: vi.fn() }) }))
vi.mock('../api/client', () => ({ api: { post: vi.fn() } }))

import { AppShell } from '../components/AppShell'

describe('mobile navigation', () => {
  it('opens with the hamburger and closes after navigation', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/']}><Routes><Route element={<AppShell/>}><Route index element={<div>Overview page</div>}/><Route path="audit" element={<div>Audit page</div>}/></Route></Routes></MemoryRouter>)
    const toggle = screen.getByRole('button', { name: 'Open navigation' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await user.click(screen.getByRole('link', { name: 'Audit' }))
    expect(await screen.findByText('Audit page')).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })
})
