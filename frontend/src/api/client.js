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
    throw new ApiError(detail||`Request failed (${response.status})`,response.status,detail)
  }
  return data
}
export const api={
  get:(path)=>request(path),
  post:(path,body)=>request(path,{method:'POST',body:body===undefined?undefined:JSON.stringify(body)}),
  put:(path,body)=>request(path,{method:'PUT',body:JSON.stringify(body)}),
  login:(values)=>request('/api/auth/login',{method:'POST',body:JSON.stringify(values)}),
  register:(values)=>request('/api/auth/register',{method:'POST',body:JSON.stringify(values)}),
  logout:()=>request('/api/auth/logout',{method:'POST'}),
}
