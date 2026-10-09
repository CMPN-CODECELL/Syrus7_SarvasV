export class ApiError extends Error {
  constructor(message, status, detail) { super(message); this.name='ApiError'; this.status=status; this.detail=detail }
}
async function request(path, options={}) {
  const response = await fetch(path,{credentials:'include',...options,headers:{...(options.body ? {'Content-Type':'application/json'}:{}),...options.headers}})
  const type=response.headers.get('content-type')||''
  const data=type.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    if (response.status===401) window.dispatchEvent(new Event('algoshield:unauthorized'))
    const detail=typeof data==='object' ? data.detail : data
    const message=typeof detail==='string' ? detail : detail?.message||detail?.code||`Request failed (${response.status})`
    throw new ApiError(message,response.status,detail)
  }
  if (path.startsWith('/api/') && !type.includes('application/json')) {
    throw new ApiError('Backend returned a non-JSON API response. Restart the FastAPI server and try again.',502,'INVALID_API_RESPONSE')
  }
  return data
}
export const api={
  get:(path)=>request(path),
  post:(path,body)=>request(path,{method:'POST',body:body===undefined?undefined:JSON.stringify(body)}),
  put:(path,body)=>request(path,{method:'PUT',body:JSON.stringify(body)}),
  selectDemoRole:(role)=>request('/api/demo-role',{method:'POST',body:JSON.stringify({role})}),
}
