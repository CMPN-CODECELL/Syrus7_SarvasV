import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'

const TelemetryContext=createContext(null)
const MAX_RETRY_DELAY_MS=10000

export function TelemetryProvider({children}){
  const {user}=useAuth()
  const accountId=user?.account_id??null
  const [snapshotState,setSnapshotState]=useState(null)
  const [status,setStatus]=useState('offline')
  const generationRef=useRef(0)

  const snapshot=snapshotState?.accountId===accountId?snapshotState.data:null
  const refresh=useCallback(async()=>{
    if(!accountId)return null
    const generation=generationRef.current
    const data=await api.get('/api/state')
    if(generation===generationRef.current){
      setSnapshotState({accountId,data})
    }
    return data
  },[accountId])

  useEffect(()=>{
    const generation=++generationRef.current
    setSnapshotState(null)
    if(!accountId){setStatus('offline');return undefined}

    let active=true
    let terminal=false
    let socket=null
    let retryTimer=null
    let retryAttempt=0
    const current=()=>active&&!terminal&&generation===generationRef.current

    const invalidateSession=()=>{
      if(!active)return
      terminal=true
      setSnapshotState(null)
      setStatus('offline')
      if(retryTimer!==null){clearTimeout(retryTimer);retryTimer=null}
      window.dispatchEvent(new Event('algoshield:unauthorized'))
    }

    const scheduleRetry=connect=>{
      if(!current()||retryTimer!==null)return
      setStatus('disconnected')
      const delay=Math.min(500*2**retryAttempt,MAX_RETRY_DELAY_MS)
      retryAttempt+=1
      retryTimer=setTimeout(()=>{
        retryTimer=null
        if(!current())return
        setStatus('retrying')
        connect()
      },delay)
    }

    const connect=async()=>{
      if(!current())return
      setStatus(retryAttempt?'retrying':'connecting')
      try{
        const data=await api.get('/api/state')
        if(!current())return
        setSnapshotState({accountId,data})
      }catch(error){
        if(!current())return
        if(error?.status===401){invalidateSession();return}
        scheduleRetry(connect)
        return
      }
      if(!current())return
      try{
        const protocol=location.protocol==='https:'?'wss':'ws'
        socket=new WebSocket(`${protocol}://${location.host}/api/stream/ws`)
      }catch{
        scheduleRetry(connect)
        return
      }
      const openedSocket=socket
      openedSocket.onopen=()=>{
        if(!current()||socket!==openedSocket)return
        retryAttempt=0
        setStatus('live')
      }
      openedSocket.onmessage=event=>{
        if(!current()||socket!==openedSocket)return
        try{setSnapshotState({accountId,data:JSON.parse(event.data)})}
        catch{setStatus('disconnected');openedSocket.close()}
      }
      openedSocket.onerror=()=>{
        if(current()&&socket===openedSocket)setStatus('disconnected')
      }
      openedSocket.onclose=event=>{
        if(socket===openedSocket)socket=null
        if(!current())return
        if(event.code===1008){invalidateSession();return}
        scheduleRetry(connect)
      }
    }

    connect()
    return()=>{
      active=false
      terminal=true
      if(retryTimer!==null)clearTimeout(retryTimer)
      if(socket){
        socket.onopen=null
        socket.onmessage=null
        socket.onerror=null
        socket.onclose=null
        socket.close()
      }
    }
  },[accountId])

  const clear=useCallback(()=>setSnapshotState(null),[])
  const value=useMemo(()=>({snapshot,status,refresh,clear}),[snapshot,status,refresh,clear])
  return <TelemetryContext.Provider value={value}>{children}</TelemetryContext.Provider>
}

export const useTelemetry=()=>useContext(TelemetryContext)
