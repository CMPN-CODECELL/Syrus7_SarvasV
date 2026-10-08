import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'
export function ProtectedRoute(){const {user,loading}=useAuth();const location=useLocation();if(loading)return <main className="center"><span className="spinner"/>Verifying session…</main>;return user?<Outlet/>:<Navigate to="/login" replace state={{from:location}}/>}
