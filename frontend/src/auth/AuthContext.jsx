import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
const AuthContext=createContext(null)
export function AuthProvider({children}) {
  const [user,setUser]=useState(null), [loading,setLoading]=useState(true), [error,setError]=useState('')
  const pendingRole=useRef(null)
  const selectRole=useCallback(async(role)=>{
    if(pendingRole.current)return pendingRole.current
    const request=api.selectDemoRole(role).then(data=>{setUser(data.user);setError('');return data.user}).catch(err=>{setUser(null);setError(err.message||'Demo role selection failed.');throw err}).finally(()=>{if(pendingRole.current===request)pendingRole.current=null;setLoading(false)})
    pendingRole.current=request
    return request
  },[])
  const refresh=useCallback(async()=>{try{const data=await api.get('/api/auth/me');setUser(data.user);setError('');return data.user}catch(err){if(err?.status===401){try{return await selectRole('trader')}catch{return null}}setUser(null);setError(err.message||'Demo role service unavailable.');return null}finally{setLoading(false)}},[selectRole])
  useEffect(()=>{refresh();const recover=()=>{setUser(null);selectRole('trader').catch(()=>{})};window.addEventListener('algoshield:unauthorized',recover);return()=>window.removeEventListener('algoshield:unauthorized',recover)},[refresh,selectRole])
  const value=useMemo(()=>({user,loading,error,selectRole,refresh}),[user,loading,error,selectRole,refresh])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
export const useAuth=()=>useContext(AuthContext)
