export function Page({eyebrow,title,description,actions,children}){return <><header className="page-head"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>{actions&&<div className="actions">{actions}</div>}</header>{children}</>}
export function Card({title,meta,children,className=''}){return <section className={`card ${className}`}><header><h2>{title}</h2>{meta&&<span className="muted">{meta}</span>}</header>{children}</section>}
export function Status({value}){const normalized=String(value??'UNKNOWN').toUpperCase();const tone=['SUCCESS','VERIFIED','HEALTHY','RUNNING','MATCHED','OPEN'].includes(normalized)?'good':['FAILED','DRIFTED','UNCERTAIN','KILLED','HALTED'].includes(normalized)?'bad':'warn';return <span className={`status ${tone}`}><i/>{normalized}</span>}
export function Money({value}){const number=Number(value);return <span className={number<0?'negative':number>0?'positive':''}>{number<0?'−':''}₹{Math.abs(number||0).toFixed(2)}</span>}
export function Empty({children='No evidence is available yet.'}){return <div className="empty">{children}</div>}
export function DataTable({columns,rows=[]}){if(!rows.length)return <Empty/>;return <div className="table-wrap"><table><thead><tr>{columns.map(c=><th key={c.key}>{c.label}</th>)}</tr></thead><tbody>{rows.map((row,i)=><tr key={row.id||row.sequence||i}>{columns.map(c=><td key={c.key}>{c.render?c.render(row):String(row[c.key]??'—')}</td>)}</tr>)}</tbody></table></div>}
const labelFor=(key)=>String(key).replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase())
const isStatus=(key)=>/status|state|health|result|verified|passed|matched/i.test(key)
function Scalar({name,value}){
  if(typeof value==='boolean')return <Status value={value?'YES':'NO'}/>
  if(value===null||value===undefined||value==='')return <span className="muted">Not available</span>
  if(isStatus(name))return <Status value={value}/>
  return <span className="evidence-value">{String(value)}</span>
}
export function EvidenceView({value,name='Evidence'}){
  if(Array.isArray(value)){
    if(!value.length)return <Empty>No {labelFor(name).toLowerCase()} available.</Empty>
    return <div className="evidence-list">{value.map((item,index)=><article className="evidence-item" key={item?.id||item?.sequence||index}><span className="evidence-index">{index+1}</span><EvidenceView value={item} name={`${name} ${index+1}`}/></article>)}</div>
  }
  if(value&&typeof value==='object')return <dl className="evidence-grid">{Object.entries(value).map(([key,item])=><div className={item&&typeof item==='object'?'evidence-field nested':'evidence-field'} key={key}><dt>{labelFor(key)}</dt><dd>{item&&typeof item==='object'?<EvidenceView value={item} name={key}/>:<Scalar name={key} value={item}/>}</dd></div>)}</dl>
  return <Scalar name={name} value={value}/>
}
export function CompactEvidence({value}){
  if(!value||typeof value!=='object')return <Scalar name="value" value={value}/>
  return <dl className="compact-evidence">{Object.entries(value).map(([key,item])=><div key={key}><dt>{labelFor(key)}</dt><dd>{item&&typeof item==='object'?<CompactEvidence value={item}/>:<Scalar name={key} value={item}/>}</dd></div>)}</dl>
}
