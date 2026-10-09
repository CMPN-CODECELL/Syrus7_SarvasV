import { Outlet } from 'react-router-dom'
import { useAuth } from './AuthContext'
export function ProtectedRoute(){const {user,loading,error,refresh}=useAuth();if(loading)return <main className="center"><span className="spinner"/>Preparing Trader workspace…</main>;if(user)return <Outlet/>;return <main className="center role-unavailable"><div><h1>Demo roles unavailable</h1><p>{error||'The backend could not select the Trader role.'}</p><button className="primary" onClick={refresh}>Retry</button></div></main>}
