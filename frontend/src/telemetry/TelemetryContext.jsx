import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
const TelemetryContext=createContext(null)
export function TelemetryProvider({children}){
  const {user}=useAuth();const [snapshot,setSnapshot]=useState(null);const [status,setStatus]=useState('offline');const reconnect=useRef(0);const stopped=useRef(false)
  const refresh=useCallback(async()=>{if(!user)return null;const data=await api.get('/api/state');setSnapshot(data);return data},[user])
  useEffect(()=>{stopped.current=false;if(!user){setSnapshot(null);setStatus('offline');return}
    let socket,timer
    const connect=async()=>{try{await refresh()}catch{return}if(stopped.current)return;setStatus('connecting');const protocol=location.protocol==='https:'?'wss':'ws';socket=new WebSocket(`${protocol}://${location.host}/api/stream/ws`);socket.onopen=()=>{reconnect.current=0;setStatus('live')};socket.onmessage=(event)=>{try{setSnapshot(JSON.parse(event.data))}catch{setStatus('degraded')}};socket.onerror=()=>setStatus('degraded');socket.onclose=(event)=>{if(stopped.current)return;if(event.code===1008){setSnapshot(null);window.dispatchEvent(new Event('algoshield:unauthorized'));return}setStatus('degraded');const delay=Math.min(1000*2**reconnect.current++,10000);timer=setTimeout(connect,delay)}}
    connect()
    return()=>{stopped.current=true;clearTimeout(timer);socket?.close()}
  },[user,refresh])
  const value=useMemo(()=>({snapshot,status,refresh,clear:()=>setSnapshot(null)}),[snapshot,status,refresh]);return <TelemetryContext.Provider value={value}>{children}</TelemetryContext.Provider>
}
export const useTelemetry=()=>useContext(TelemetryContext)
