import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
const AuthContext=createContext(null)
export function AuthProvider({children}) {
  const [user,setUser]=useState(null), [loading,setLoading]=useState(true)
  const refresh=useCallback(async()=>{try{const data=await api.get('/api/auth/me');setUser(data.user);return data.user}catch{setUser(null);return null}finally{setLoading(false)}},[])
  useEffect(()=>{refresh();const clear=()=>setUser(null);window.addEventListener('algoshield:unauthorized',clear);return()=>window.removeEventListener('algoshield:unauthorized',clear)},[refresh])
  const login=async(values)=>{const data=await api.login(values);setUser(data.user);return data.user}
  const register=async(values)=>{const data=await api.register(values);setUser(data.user);return data.user}
  const logout=async()=>{try{await api.logout()}finally{setUser(null)}}
  const value=useMemo(()=>({user,loading,login,register,logout,refresh}),[user,loading,refresh])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
export const useAuth=()=>useContext(AuthContext)
