import { render,screen } from '@testing-library/react'
import { MemoryRouter,Route,Routes } from 'react-router-dom'
import { describe,expect,it,vi } from 'vitest'
let auth={user:null,loading:false}
vi.mock('../auth/AuthContext',()=>({useAuth:()=>auth}))
import { ProtectedRoute } from '../auth/ProtectedRoute'
describe('protected routes',()=>{
  it('shows a retryable role error instead of a sign-in screen',()=>{auth={user:null,loading:false,error:'role unavailable',refresh:vi.fn()};render(<MemoryRouter initialEntries={['/risk']}><Routes><Route element={<ProtectedRoute/>}><Route path="/risk" element={<h1>Risk</h1>}/></Route></Routes></MemoryRouter>);expect(screen.getByText('Demo roles unavailable')).toBeInTheDocument();expect(screen.queryByText('Sign in')).not.toBeInTheDocument()})
  it('renders the route for an authenticated user',()=>{auth={user:{username:'tester'},loading:false};render(<MemoryRouter initialEntries={['/risk']}><Routes><Route path="/login" element={<h1>Sign in</h1>}/><Route element={<ProtectedRoute/>}><Route path="/risk" element={<h1>Risk center</h1>}/></Route></Routes></MemoryRouter>);expect(screen.getByText('Risk center')).toBeInTheDocument()})
})
