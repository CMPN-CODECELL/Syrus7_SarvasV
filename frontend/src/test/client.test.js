import { afterEach,describe,expect,it,vi } from 'vitest'
import { ApiError,api } from '../api/client'
afterEach(()=>vi.restoreAllMocks())
describe('API client',()=>{
  it('always includes cookie credentials',async()=>{vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify({ok:true}),{status:200,headers:{'Content-Type':'application/json'}}));await api.get('/api/state');expect(fetch).toHaveBeenCalledWith('/api/state',expect.objectContaining({credentials:'include'}))})
  it('normalizes backend errors',async()=>{vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify({detail:'denied'}),{status:403,headers:{'Content-Type':'application/json'}}));await expect(api.get('/api/state')).rejects.toMatchObject({name:'ApiError',status:403,detail:'denied'});expect(ApiError.prototype).toBeInstanceOf(Error)})
  it('broadcasts session invalidation on 401',async()=>{const listener=vi.fn();window.addEventListener('algoshield:unauthorized',listener);vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify({detail:'expired'}),{status:401,headers:{'Content-Type':'application/json'}}));await expect(api.get('/api/state')).rejects.toBeInstanceOf(ApiError);expect(listener).toHaveBeenCalledOnce();window.removeEventListener('algoshield:unauthorized',listener)})
})
