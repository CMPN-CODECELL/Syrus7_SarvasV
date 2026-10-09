import { useEffect,useRef,useState } from 'react';import { useOutletContext } from 'react-router-dom';import { api } from '../api/client';import { useAuth } from '../auth/AuthContext';import { Card,CompactEvidence,DataTable,Empty,EvidenceView,Page,Status } from '../components/UI';import { CandleChart } from '../components/CandleChart'
function RemotePage({endpoint,eyebrow,title,description,render,children}){const [data,setData]=useState(null),[error,setError]=useState('');useEffect(()=>{api.get(endpoint).then(setData).catch(e=>setError(e.status===404?'No completed evidence yet.':e.message))},[endpoint]);return <Page eyebrow={eyebrow} title={title} description={description}>{children}{error?<Empty>{error}</Empty>:data?render(data):<Empty>Loading backend evidence…</Empty>}</Page>}
const reconciliationLabel=value=>String(value).replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase())
const hasReconciliationDetails=value=>value&&typeof value==='object'&&(Array.isArray(value)?value.length>0:Object.keys(value).length>0)
const reconciliationSections=value=>({summary:Object.fromEntries(Object.entries(value||{}).filter(([,item])=>!item||typeof item!=='object')),details:Object.entries(value||{}).filter(([,item])=>hasReconciliationDetails(item))})
export function ReconciliationView({data}){const report=data.report||{};const reportSections=reconciliationSections(report);const comparisonSections=reconciliationSections(data.position_comparison);const events=(data.events||[]).map(event=>({...event,payload:auditEvidence(event.payload)}));const pending=!report.verified&&report.reason==='STARTUP_RECONCILIATION_REQUIRED';const brokerUnavailable=!report.verified&&!data.broker?.last_verified_at;return <><div className="reconciliation-summary"><Card title="Verification"><Status value={report.verified?'VERIFIED':pending?'PENDING':'FAILED'}/></Card><Card title="Reason"><strong>{report.reason||'UNKNOWN'}</strong></Card><Card title="Unknown orders"><strong>{data.unknown_orders?.length||0}</strong></Card></div>{pending&&<div className="reconciliation-notice" role="status">Broker state has not been verified since startup. This is pending evidence, not a confirmed position mismatch. An authorized operator must obtain broker evidence and reconcile before explicit resume can open trading.</div>}<div className="reconciliation-stack"><Card title="Position comparison"><CompactEvidence value={comparisonSections.summary}/>{comparisonSections.details.length>0?<div className="reconciliation-details">{comparisonSections.details.map(([name,value])=><section key={name}><h3>{reconciliationLabel(name)}</h3><EvidenceView value={value} name={name}/></section>)}</div>:<p className="reconciliation-clear">{brokerUnavailable?'Broker position evidence is unavailable; drift is not confirmed.':'No broker or virtual position differences reported.'}</p>}</Card><Card title="Broker evidence"><CompactEvidence value={data.broker}/></Card><Card title="Recovery report"><CompactEvidence value={reportSections.summary}/>{reportSections.details.length>0&&<div className="reconciliation-details">{reportSections.details.map(([name,value])=><section key={name}><h3>{reconciliationLabel(name)}</h3><EvidenceView value={value} name={name}/></section>)}</div>}</Card>{events.length>0&&<Card title="Recent reconciliation events"><EvidenceView value={events} name="events"/></Card>}</div></>}
export function ReconciliationPage(){
  const {refresh}=useOutletContext()||{};
  const {user,refresh:refreshAuth}=useAuth()||{};
  const isOperator=Boolean(user?.is_operator);
  const [busy,setBusy]=useState('');
  const [error,setError]=useState('');
  const run=async action=>{
    if(busy||!isOperator)return;
    setBusy(action);setError('');
    try{await api.post(`/api/broker/${action}`);await refresh?.()}
    catch(e){
      if(e?.status===403){await refreshAuth?.()}
      setError(e.message||'Broker control failed.')
    }finally{setBusy('')}
  };
  const disconnect=()=>{if(!isOperator)return;if(confirm('Disconnect the broker and fail closed?'))run('disconnect')};
  return <RemotePage endpoint="/api/reconciliation" eyebrow="Recovery" title="Reconciliation center" description="Expected local state compared with observed broker truth." render={data=><ReconciliationView data={data}/>}> 
    {error&&<div className="error" role="alert">{error}</div>}
    <Card title="Broker controls">
      <p className="muted">
        {isOperator
          ? 'Operator-only controls. Reconnect always reconciles before trading can resume.'
          : 'Operator authority required to use broker controls.'}
      </p>
      <div className="actions">
        <button type="button" disabled={!!busy||!isOperator} title={!isOperator?'Operator authority required':undefined} onClick={()=>run('updates/sync')}>{busy==='updates/sync'?'Syncing…':'Sync broker updates'}</button>
        <button type="button" disabled={!!busy||!isOperator} title={!isOperator?'Operator authority required':undefined} onClick={()=>run('reconnect')}>{busy==='reconnect'?'Reconnecting…':'Reconnect and reconcile'}</button>
        <button type="button" disabled={!!busy||!isOperator} title={!isOperator?'Operator authority required':undefined} onClick={disconnect}>{busy==='disconnect'?'Disconnecting…':'Disconnect broker'}</button>
      </div>
    </Card>
  </RemotePage>
}
export function TracesPage(){
  return (
    <RemotePage endpoint="/api/traces" eyebrow="Causality" title="Execution traces" description="Server-built timelines connect intent, risk, order, fill, and reconciliation evidence." render={d=><Card title="Recent traces"><DataTable rows={Array.isArray(d)?d:d.traces||[]} columns={[{key:'trace_id',label:'Trace'},{key:'strategy_instance_id',label:'Strategy'},{key:'account_id',label:'Account'},{key:'events',label:'Events',render:r=>Array.isArray(r.events)?r.events.length:'—'},{key:'recorded_at',label:'First recorded',render:r=>r.events?.[0]?.recorded_at??'—'}]}/></Card>}/>
  )
}
const FAILURE_GUIDE={
  partial:{title:'Partial order fill',summary:'The broker fills only part of an order.',pass:'Only the executed quantity was counted; the unfilled quantity did not become a position.'},
  rejection:{title:'Broker rejection',summary:'The broker refuses an approved order.',pass:'The rejected order created no fill and no trading position.'},
  position_limit:{title:'Position limit',summary:'A new order would exceed the strategy’s size limit.',pass:'AlgoShield blocked the extra order before it reached the broker.'},
  duplicate_fill:{title:'Duplicate fill',summary:'The broker sends the same trade confirmation twice.',pass:'The duplicate was ignored, so position and P&L were not counted twice.'},
  conflicting_fill:{title:'Conflicting fill',summary:'The same fill ID arrives with different trade details.',pass:'AlgoShield rejected the conflict and closed the trading gate for review.'},
  missed_fill:{title:'Missed fill recovery',summary:'A broker fill is initially missing from local records.',pass:'Reconciliation found the real fill and repaired local state from broker evidence.'},
  unknown_submission:{title:'Unknown order outcome',summary:'The broker accepts an order but the response times out.',pass:'The order stayed UNKNOWN and AlgoShield did not blindly submit it again.'},
  disconnect:{title:'Broker disconnect',summary:'The broker connection drops.',pass:'AlgoShield stopped trusting broker state and blocked new risk.'},
  reconnect:{title:'Broker reconnect',summary:'The broker connection becomes available again.',pass:'Connectivity returned without silently declaring trading safe.'},
  spam:{title:'Too many orders',summary:'A strategy sends orders faster than its rate limit.',pass:'Orders over the allowed rate were blocked by the platform.'},
  stale_feed:{title:'Stale market feed',summary:'The latest market price becomes too old to trust.',pass:'AlgoShield blocked a new order instead of trading on stale data.'},
  drift:{title:'Unexpected broker position',summary:'The broker reports a position AlgoShield cannot explain.',pass:'Reconciliation detected the mismatch and failed closed.'},
  clear_drift:{title:'Clear position drift',summary:'The injected broker mismatch is removed and checked again.',pass:'AlgoShield rechecked broker truth instead of clearing the warning blindly.'},
  kill_partial:{title:'Kill after partial fill',summary:'The kill switch runs while an order is partly filled.',pass:'The platform cancelled or closed remaining exposure and verified the result.'},
  broker_update:{title:'Broker update stream',summary:'A partial fill arrives as a broker event.',pass:'The event updated the order and position using actual fill evidence.'},
  disconnect_recovery:{title:'Recover after disconnect',summary:'A fill happens while the platform is disconnected.',pass:'Reconnect reconciliation recovered the missed fill and synchronized local state.'},
  concurrent_position_race:{title:'Simultaneous orders',summary:'Two orders try to use the same position capacity at once.',pass:'Atomic risk checks allowed only the order that fit within the limit.'},
  account_risk:{title:'Account net limit',summary:'A trade would push the whole account beyond its net limit.',pass:'The account-level risk rule blocked the trade.'},
  opposing_gross_exposure:{title:'Opposing strategy exposure',summary:'Opposing trades hide risk when only the net position is viewed.',pass:'AlgoShield measured gross strategy exposure and blocked the excess.'},
  limit_lowered_below_position:{title:'Limit reduced below position',summary:'A position is already larger than a newly lowered limit.',pass:'Increasing risk was blocked while a reducing trade remained allowed.'},
  daily_loss_mark_breach:{title:'Daily loss limit',summary:'A price move takes the strategy beyond its daily loss limit.',pass:'AlgoShield blocked further risk after the loss threshold was breached.'},
  late_fill_after_cancel:{title:'Late fill after cancel',summary:'A fill arrives after cancellation was requested.',pass:'The late execution was still recorded because fills remain financial truth.'},
  kill_late_fill:{title:'Late fill during kill',summary:'An execution arrives while the kill switch is closing exposure.',pass:'The kill process included the late fill before verifying the final state.'},
  broker_failure_during_kill:{title:'Broker failure during kill',summary:'The broker becomes unavailable during the kill process.',pass:'AlgoShield reported uncertainty instead of claiming the account was flat.'},
  restart_fail_closed:{title:'Restart safety',summary:'The platform restarts after trading activity.',pass:'It restarted with trading closed until reconciliation and explicit resume.'},
  stale_broker_evidence:{title:'Stale broker evidence',summary:'The last broker snapshot is too old to trust.',pass:'AlgoShield blocked new exposure until fresh broker evidence is available.'},
  invalid_price:{title:'Unreasonable limit price',summary:'A limit order price is far from the trusted market mark.',pass:'The price-reasonability rule blocked the order.'},
};
const guideFor=(scenario,details)=>{const remote=details?.[scenario];const fallback=FAILURE_GUIDE[scenario]||{title:String(scenario).replaceAll('_',' ').replace(/\b\w/g,l=>l.toUpperCase()),summary:'A controlled reliability condition is injected into the local mock platform.',pass:'The scenario met its backend-defined safety check.'};return {id:scenario,title:remote?.title||fallback.title,summary:remote?.summary||fallback.summary,what_it_does:remote?.what_it_does||remote?.summary||fallback.summary,steps:remote?.steps||['Initialize mock environment','Inject failure condition','Run platform risk and execution checks','Verify safety invariants and local state'],parameters:remote?.parameters||[],pass:fallback.pass};};
const gateCopy={RUNNING:'Trading gate is open.',STOPPED:'Trading is stopped; review the result before resuming.',UNCERTAIN:'New risk is blocked until the platform is reconciled.',KILLED:'The kill switch remains latched.',KILLING:'The platform is still closing exposure.',RECOVERING:'Broker truth must be checked before trading.'};
const reasonCopy={ALLOWED:'Order passed the risk checks.',RISK_MAX_POSITION:'Blocked by the position-size limit.',RISK_RATE_LIMIT:'Blocked by the order-rate limit.',RISK_MAX_DAILY_LOSS:'Blocked by the daily-loss limit.',RISK_ACCOUNT_NET_POSITION:'Blocked by the account net-position limit.',RISK_ACCOUNT_GROSS_POSITION:'Blocked by the account gross-exposure limit.',RISK_STALE_BROKER_STATE:'Blocked because broker evidence was stale.',RISK_STALE_MARKET_DATA:'Blocked because market data was stale.',RISK_PRICE_REASONABILITY:'Blocked because the order price was unreasonable.',RISK_GLOBAL_GATE:'Blocked because the global trading gate was closed.'};
const decisionReasons=result=>[...new Set((result?.decisions||[]).map(item=>item?.reason_code).filter(Boolean))];

function FailureTechnicalEvidence({result}){
  const gate=String(result.state?.gate||'UNKNOWN');
  const health=String(result.state?.health||'UNKNOWN');
  const duration=Math.round(Number(result.duration_ms)||0);
  const evidenceEntries=result.evidence&&typeof result.evidence==='object'
    ?Object.entries(result.evidence).filter(([,v])=>v!==undefined&&v!==null&&typeof v!=='function')
    :[];
  const decisions=Array.isArray(result.decisions)?result.decisions:[];
  const invariants=Array.isArray(result.invariants?.invariants)?result.invariants.invariants:[];

  const rawClean={
    scenario:result.scenario,
    status:result.status,
    duration_ms:duration,
    gate,
    health,
    observed_evidence:result.evidence,
    decisions:decisions.map(d=>({
      intent_id:d.intent_id,
      allowed:d.allowed,
      reason_code:d.reason_code,
      reason_text:d.reason_text
    }))
  };

  return(
    <div className="lab-technical-content">
      <div className="lab-tech-summary-grid">
        <div className="lab-tech-field">
          <span>Scenario</span>
          <strong>{result.scenario}</strong>
        </div>
        <div className="lab-tech-field">
          <span>Test Status</span>
          <Status value={result.status}/>
        </div>
        <div className="lab-tech-field">
          <span>Duration</span>
          <strong>{duration} ms</strong>
        </div>
        <div className="lab-tech-field">
          <span>Gate / Health</span>
          <strong>{gate} · {health}</strong>
        </div>
      </div>

      {evidenceEntries.length>0&&(
        <div className="lab-tech-section">
          <h4>Observed Test Evidence</h4>
          <div className="lab-tech-evidence-grid">
            {evidenceEntries.map(([k,v])=>(
              <div key={k} className="lab-tech-pill">
                <span>{k.replace(/_/g,' ')}</span>
                <strong>{typeof v==='object'?JSON.stringify(v):String(v)}</strong>
              </div>
            ))}
          </div>
        </div>
      )}

      {decisions.length>0&&(
        <div className="lab-tech-section">
          <h4>Risk Decisions Evaluated ({decisions.length})</h4>
          <div className="lab-tech-decisions-list">
            {decisions.map((d,i)=>(
              <div key={d.intent_id||i} className={`lab-tech-decision-card ${d.allowed?'allowed':'blocked'}`}>
                <div className="lab-tech-decision-head">
                  <code>{d.intent_id||`Intent #${i+1}`}</code>
                  <span className={`status ${d.allowed?'good':'bad'}`}>
                    <i></i>{d.allowed?'ALLOWED':'BLOCKED'}
                  </span>
                </div>
                <div className="lab-tech-decision-body">
                  <strong>{d.reason_code||(d.allowed?'ALLOWED':'REJECTED')}</strong>
                  {d.reason_text&&<p>{d.reason_text}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {invariants.length>0&&(
        <div className="lab-tech-section">
          <h4>Safety Invariants Audited</h4>
          <div className="lab-tech-invariants-list">
            {invariants.slice(0,6).map(inv=>(
              <div key={inv.id||inv.name} className="lab-tech-invariant-item">
                <span className="inv-name">{inv.name||inv.id}</span>
                <Status value={inv.status}/>
              </div>
            ))}
          </div>
        </div>
      )}

      <details className="lab-tech-raw">
        <summary>View raw JSON payload</summary>
        <pre>{JSON.stringify(rawClean,null,2)}</pre>
      </details>
    </div>
  );
}

function FailureResult({result,details}){
  const guide=guideFor(result.scenario,details);
  const passed=result.status==='PASS';
  const gate=String(result.state?.gate||'UNKNOWN');
  const reasons=decisionReasons(result);
  const explanation=result.explanation||guide.pass;
  const simpleEvidence=result.simple_evidence&&Object.keys(result.simple_evidence).length>0?result.simple_evidence:null;
  const paramsUsed=result.parameters_used&&Object.keys(result.parameters_used).length>0?result.parameters_used:null;

  return (
    <section className={`lab-result ${passed?'pass':'fail'}`} aria-labelledby="lab-result-title" tabIndex="-1">
      <div className="lab-result-mark" aria-hidden="true">{passed?'✓':'!'}</div>
      <div className="lab-result-main">
        <span className="lab-kicker">Test complete · <Status value={result.status}/></span>
        <h2 id="lab-result-title">{passed?'Protection worked as expected':'The safety check did not pass'}</h2>
        <p className="lab-result-summary">{explanation}</p>

        {simpleEvidence&&(
          <div className="lab-simple-evidence">
            <h3>Key Evidence at a Glance</h3>
            <div className="simple-evidence-grid">
              {Object.entries(simpleEvidence).map(([label,value])=>(
                <div key={label} className="simple-evidence-chip">
                  <span className="simple-evidence-label">{label}</span>
                  <strong className="simple-evidence-value">
                    {typeof value==='boolean'?(value?'Verified Safe':'Breached'):String(value)}
                  </strong>
                </div>
              ))}
            </div>
          </div>
        )}

        {paramsUsed&&(
          <div className="lab-params-used">
            <span>Parameters used:</span>
            <div className="lab-params-pills">
              {Object.entries(paramsUsed).map(([k,v])=>(
                <code key={k}>{k}: {String(v)}</code>
              ))}
            </div>
          </div>
        )}

        <div className="lab-result-facts">
          <div><span>Test</span><strong>{result.title||guide.title}</strong></div>
          <div><span>Finished in</span><strong>{Math.round(Number(result.duration_ms)||0)} ms</strong></div>
          <div><span>Trading gate</span><strong>{gate}</strong><small>{gateCopy[gate]||'Check the technical evidence for the current gate state.'}</small></div>
          <div><span>Platform health</span><strong>{String(result.state?.health||'UNKNOWN')}</strong></div>
        </div>

        {reasons.length>0&&(
          <div className="lab-decisions">
            <h3>Risk decisions made</h3>
            <ul>
              {reasons.map(reason=>(
                <li key={reason}>
                  <b>{reasonCopy[reason]||'The platform recorded this backend risk decision.'}</b>
                  <code>{reason}</code>
                </li>
              ))}
            </ul>
          </div>
        )}

        <details className="lab-technical">
          <summary>View technical evidence</summary>
          <p>Concise execution audit, risk evaluations, and safety checks for this run.</p>
          <FailureTechnicalEvidence result={result}/>
        </details>
      </div>
    </section>
  );
}

export function FailureLabPage(){
  const {snapshot} = useOutletContext() || {};
  const {user,refresh:refreshAuth} = useAuth() || {};
  const isOperator = Boolean(user?.is_operator);
  const [scenarios,setScenarios]=useState([]);
  const [details,setDetails]=useState({});
  const [selectedScenario,setSelectedScenario]=useState('partial');
  const [scenarioParams,setScenarioParams]=useState({});
  const [result,setResult]=useState(null);
  const [busy,setBusy]=useState('');
  const [activeStepIndex,setActiveStepIndex]=useState(0);
  const [error,setError]=useState('');
  const resultRef=useRef(null);
  const mockLabEnabled=snapshot?.failure_lab_enabled!==false;
  const isolatedLab=snapshot?.demo_enabled===false;

  useEffect(()=>{
    api.get('/api/failure-lab/scenarios')
      .then(data=>{
        if(!Array.isArray(data?.scenarios))throw new Error('Invalid Failure Lab scenario response');
        setScenarios(data.scenarios);
        if(data.details&&typeof data.details==='object'){
          setDetails(data.details);
        }
        if(data.scenarios.length>0){
          setSelectedScenario(prev=>prev&&data.scenarios.includes(prev)?prev:data.scenarios[0]);
        }
      })
      .catch(e=>{
        setScenarios([]);
        setError(e.message);
      });
  },[]);

  useEffect(()=>{
    if(result)resultRef.current?.focus();
  },[result]);

  useEffect(()=>{
    if(!busy){
      setActiveStepIndex(0);
      return;
    }
    const currentSteps=guideFor(busy,details).steps;
    const total=currentSteps.length||4;
    setActiveStepIndex(0);
    const interval=setInterval(()=>{
      setActiveStepIndex(prev=>{
        if(prev<total-1)return prev+1;
        return prev;
      });
    },300);
    return()=>clearInterval(interval);
  },[busy,details]);

  const getParamsFor=scenario=>{
    const meta=details[scenario]||{};
    const defaults={};
    if(Array.isArray(meta.parameters)){
      for(const p of meta.parameters){
        defaults[p.name]=p.default;
      }
    }
    return{...defaults,...(scenarioParams[scenario]||{})};
  };

  const updateParam=(scenario,name,value)=>{
    setScenarioParams(prev=>({
      ...prev,
      [scenario]:{
        ...getParamsFor(scenario),
        [name]:value
      }
    }));
  };

  const run=async(scenario,customParams)=>{
    if(!isOperator){
      setError('Operator authority required to run Failure Lab scenarios.');
      return;
    }
    if(!mockLabEnabled){
      setError('Failure Lab is temporarily unavailable.');
      return;
    }
    if(busy||!confirm(`Run ${guideFor(scenario,details).title}? ${isolatedLab?'This runs in an isolated mock sandbox and cannot change live 021 state.':'This will mutate the current mock platform and may change its safety, order, fill, or position state.'}`))return;
    const paramsToSend=customParams||getParamsFor(scenario);
    setBusy(scenario);
    setSelectedScenario(scenario);
    setResult(null);
    setError('');
    try{
      setResult(await api.post(`/api/failure-lab/${scenario}`,paramsToSend));
    }catch(e){
      if(e?.status===403){await refreshAuth?.()}
      setError(e.message);
    }finally{
      setBusy('');
    }
  };

  const activeGuide=guideFor(selectedScenario,details);
  const runningGuide=busy?guideFor(busy,details):null;

  return(
    <Page eyebrow="Practice a failure safely" title="Failure Lab" description="Simulate broker and market failures to verify risk and recovery protections in real time.">
      <p className="muted">{isolatedLab?'These tests run in an isolated offline sandbox and cannot change 021 orders, fills, positions, or market data.':'These tests mutate the current mock platform.'} Review the selected scenario, then confirm before running it.</p>
      {isolatedLab&&<div className="notice" role="status">021 virtual-exchange mode is active. Failure Lab runs against an isolated mock sandbox; live provider state remains untouched.</div>}
      {error&&<div className="error" role="alert">{error}</div>}

      {busy&&runningGuide&&(
        <section className="lab-running" role="status" aria-live="polite">
          <div className="lab-pulse"/>
          <div className="lab-running-main">
            <div className="lab-running-header">
              <span>Running mock test</span>
              <h2>{runningGuide.title}</h2>
              <p>{runningGuide.summary} Waiting for verified backend evidence…</p>
            </div>
            <div className="lab-live-steps">
              <span className="lab-live-steps-title">What AlgoShield is doing right now:</span>
              <ol className="lab-steps-list">
                {runningGuide.steps.map((stepText,idx)=>{
                  const isDone=idx<activeStepIndex;
                  const isCurrent=idx===activeStepIndex;
                  return(
                    <li key={idx} className={`lab-step-item ${isDone?'done':isCurrent?'current':'pending'}`}>
                      <span className="lab-step-bullet">{isDone?'✓':isCurrent?'▶':String(idx+1)}</span>
                      <span className="lab-step-text">{stepText}</span>
                      {isCurrent&&<span className="lab-step-active-tag">In progress…</span>}
                    </li>
                  );
                })}
              </ol>
            </div>
          </div>
        </section>
      )}

      {selectedScenario&&(
        <section className="lab-inspector-card" aria-label="Test configuration and explanation">
          <header className="lab-inspector-header">
            <div>
              <span className="lab-kicker">Interactive Test Inspector</span>
              <h2>{activeGuide.title}</h2>
              <p className="lab-inspector-desc">{activeGuide.what_it_does}</p>
            </div>
            {scenarios.length>1&&(
              <div className="lab-scenario-picker">
                <label htmlFor="test-select">Select test:</label>
                <select id="test-select" value={selectedScenario} onChange={e=>setSelectedScenario(e.target.value)} disabled={!!busy}>
                  {scenarios.map(s=>(
                    <option key={s} value={s}>{guideFor(s,details).title}</option>
                  ))}
                </select>
              </div>
            )}
          </header>

          <div className="lab-inspector-body">
            <div className="lab-inspector-steps">
              <h3>What happens during this test</h3>
              <ol>
                {activeGuide.steps.map((st,i)=>(
                  <li key={i}>{st}</li>
                ))}
              </ol>
            </div>

            {activeGuide.parameters&&activeGuide.parameters.length>0&&(
              <div className="lab-inspector-params">
                <h3>Customizable test parameters</h3>
                <div className="lab-params-grid">
                  {activeGuide.parameters.map(param=>{
                    const currentVal=getParamsFor(selectedScenario)[param.name]??param.default;
                    return(
                      <div key={param.name} className="lab-param-field">
                        <label htmlFor={`param-${selectedScenario}-${param.name}`}>
                          <b>{param.label}</b>
                          {param.description&&<small>{param.description}</small>}
                        </label>
                        <div className="lab-param-input-group">
                          <input
                            id={`param-${selectedScenario}-${param.name}`}
                            type={param.type==='number'?'number':'text'}
                            min={param.min}
                            max={param.max}
                            step={param.step||(param.type==='number'?1:undefined)}
                            value={currentVal}
                            disabled={!!busy}
                            onChange={e=>{
                              const v=param.type==='number'?Number(e.target.value):e.target.value;
                              updateParam(selectedScenario,param.name,v);
                            }}
                          />
                          {currentVal!==param.default&&(
                            <button
                              type="button"
                              className="ghost lab-param-reset"
                              onClick={()=>updateParam(selectedScenario,param.name,param.default)}
                              disabled={!!busy}
                            >
                              Reset ({param.default})
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          <div className="lab-inspector-footer">
            <button
              type="button"
              className="primary lab-inspector-run"
              aria-label="Run selected scenario with configured parameters"
              disabled={!!busy||!mockLabEnabled||!isOperator}
              onClick={()=>run(selectedScenario)}
            >
              {busy===selectedScenario?'Running mock test…':!isOperator?'Run scenario (Operator required)':`Run ${activeGuide.title} with configured parameters`}
            </button>
          </div>
        </section>
      )}

      <section className="lab-scenarios" aria-labelledby="scenario-title">
        <header>
          <h2 id="scenario-title">What would you like to test?</h2>
        </header>
        {scenarios.length?(
          <div className="scenario-grid">
            {scenarios.map(s=>{
              const guide=guideFor(s,details);
              const isBusy=busy===s;
              const isSelected=selectedScenario===s;
              return(
                <div
                  key={s}
                  className={`scenario-card ${isSelected?'selected':''} ${isBusy?'active':''}`}
                  onClick={()=>setSelectedScenario(s)}
                >
                  <div className="scenario-card-head">
                    <b>{guide.title}</b>
                    {guide.parameters&&guide.parameters.length>0&&(
                      <span className="scenario-param-tag">
                        {guide.parameters.length} {guide.parameters.length===1?'parameter':'params'}
                      </span>
                    )}
                  </div>
                  <span>{guide.summary}</span>
                  <div className="scenario-card-actions">
                    <button
                      type="button"
                      className={`scenario-run-btn ${isBusy?'active':''}`}
                      disabled={!!busy||!mockLabEnabled||!isOperator}
                      onClick={e=>{
                        e.stopPropagation();
                        setSelectedScenario(s);
                        run(s);
                      }}
                      aria-label={`Run ${guide.title} mock test`}
                    >
                      {isBusy?'Test running…':!isOperator?'Operator required':isolatedLab?'Run in isolated sandbox':'Run on current mock platform'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ):!error&&(
          <Empty>Loading available failure scenarios…</Empty>
        )}
      </section>

      {result&&(
        <div ref={resultRef}>
          <FailureResult result={result} details={details}/>
        </div>
      )}
    </Page>
  );
}
export function SafetyBenchPage(){
  const {user,refresh:refreshAuth}=useAuth()
  const isOperator=Boolean(user?.is_operator)
  const [data,setData]=useState(null)
  const [busy,setBusy]=useState(false)
  const [iterations,setIterations]=useState(25)
  const [error,setError]=useState('')
  useEffect(()=>{api.get('/api/safety-bench/latest').then(setData).catch(()=>{})},[])
  const run=async()=>{
    if(busy||!isOperator)return
    setBusy(true)
    setError('')
    try{
      setData(await api.post('/api/safety-bench/run',{iterations}))
    }catch(runError){
      if(runError?.status===403){await refreshAuth?.()}
      setError(runError.message||'Benchmark failed.')
    }finally{
      setBusy(false)
    }
  }
  return <Page eyebrow="Isolated benchmark" title="SafetyBench" description="Bounded reliability tests run away from live platform state." actions={<div className="bench-control"><label>Iterations<input type="number" min="1" max="100" value={iterations} onChange={e=>setIterations(Number(e.target.value))}/></label><button className="primary" disabled={busy||!isOperator} title={!isOperator?'Operator authority required':undefined} onClick={run}>{busy?'Running…':!isOperator?'Run benchmark (Operator required)':'Run benchmark'}</button></div>}>{error&&<div className="error" role="alert">{error}</div>}{data?<Card title="Latest completed run"><EvidenceView value={data}/></Card>:<Empty>No completed benchmark run.</Empty>}</Page>
}
export function MetricsPage(){return <RemotePage endpoint="/api/metrics" eyebrow="Process diagnostics" title="Operational metrics" description="Bounded runtime counters—not financial truth." render={d=><div className="grid two"><Card title="Counters"><EvidenceView value={d.counters||d}/></Card><Card title="Latency observations"><EvidenceView value={d.observations||{}}/></Card></div>}/>}
export function MarketDataPage(){
  const {user,refresh:refreshAuth}=useAuth()
  const isOperator=Boolean(user?.is_operator)
  const {snapshot:s,accountId}=useOutletContext()
  const [symbol,setSymbol]=useState('')
  const [symbolQuery,setSymbolQuery]=useState('')
  const [interval,setInterval]=useState(60)
  const [history,setHistory]=useState([])
  const [historyError,setHistoryError]=useState('')
  const [historyLoading,setHistoryLoading]=useState(false)
  const [displayLimit,setDisplayLimit]=useState(50)
  const [watchlist,setWatchlist]=useState(()=>{try{return JSON.parse(localStorage.getItem('algoshield.watchlist')||'[]')}catch{return []}})
  const quotes=Array.isArray(s?.market_data?.latest_quotes)?s.market_data.latest_quotes:[]
  const symbols=[...new Set([
    ...(s?.market_data?.canonical_symbols||[]),
    ...(s?.market_data?.symbols||[]),
    ...quotes.map(item=>item.symbol),
    ...(s?.candles||[]).map(item=>item.symbol),
    ...(s?.subscriptions||[]).map(item=>item.symbol),
  ].filter(Boolean))].sort()
  const filteredSymbols=symbols.filter(value=>value.toLowerCase().includes(symbolQuery.trim().toLowerCase()))
  const matchesQuery=item=>!symbolQuery.trim()||item.symbol?.toLowerCase().includes(symbolQuery.trim().toLowerCase())
  const forming=s?.market_data?.forming_candles||[]
  const liveClosed=(s?.candles||[]).filter(item=>(!symbol||item.symbol===symbol)&&matchesQuery(item))
  const [sessionBusy,setSessionBusy]=useState(false)
  const [sessionError,setSessionError]=useState('')
  const setSession=async status=>{
    if(sessionBusy||!isOperator)return
    setSessionBusy(true)
    setSessionError('')
    try{
      await api.post('/api/market/session',{status})
    }catch(e){
      if(e?.status===403){await refreshAuth?.()}
      setSessionError(e.message||'Market session update failed.')
    }finally{
      setSessionBusy(false)
    }
  }
  const visibleQuotes=quotes.filter(item=>(!symbol||item.symbol===symbol)&&matchesQuery(item))
  const displayedQuotes=visibleQuotes.slice(0,displayLimit)
  const watchQuotes=quotes.filter(item=>watchlist.includes(item.symbol))
  const toggleWatch=symbol=>setWatchlist(current=>current.includes(symbol)?current.filter(item=>item!==symbol):[...current,symbol])
  useEffect(()=>{localStorage.setItem('algoshield.watchlist',JSON.stringify(watchlist))},[watchlist])
  useEffect(()=>{let active=true;setHistory([]);setHistoryError('');setHistoryLoading(true);const query=new URLSearchParams({interval:String(interval),limit:'200'});if(symbol)query.set('symbol',symbol);Promise.resolve().then(()=>api.get(`/api/candles?${query}`)).then(rows=>{if(active)setHistory(Array.isArray(rows)?rows:[])}).catch(error=>{if(active)setHistoryError(error.message||'Historical candles unavailable.')}).finally(()=>{if(active)setHistoryLoading(false)});return()=>{active=false}},[accountId,interval,symbol])
  const historicalRows=[...new Map([...history,...liveClosed].filter(item=>matchesQuery(item)).map(item=>[`${item.symbol}:${item.interval}:${item.start_time}`,item])).values()].sort((a,b)=>a.start_time-b.start_time)
  const formingRows=forming.filter(item=>(!symbol||item.symbol===symbol)&&matchesQuery(item)&&Number(item.interval)===interval)
  const source=s?.market_data?.label||s?.market_data?.provider||'Unavailable'
  const eventTime=typeof s?.market_data?.last_event_timestamp==='number'?s.market_data.last_event_timestamp:Math.max(0,...quotes.map(item=>Number(item.event_timestamp)||0))||null
  const asUtc=value=>{
    const numeric=Number(value)
    return value===null||value===undefined||!Number.isFinite(numeric)?'—':new Date(numeric*1000).toISOString()
  }
  return <Page className="market-data-page" eyebrow="Market ingestion" title="Market data" description="Provider observations, forming bars, and finalized candle history from the backend.">
    {sessionError&&<div className="error" role="alert">{sessionError}</div>}
    <div className="stat-grid">
      <Card title="Market feed"><strong>{s?.market_data?.feed_status||'UNKNOWN'}</strong><p>{source} · {s?.market_data?.connected?'Transport connected':'Transport disconnected'}</p></Card>
      <Card title="Safety gate"><Status value={s?.gate}/></Card>
      <Card title="Feed age"><strong>{s?.market_data?.feed_age_seconds==null?'Unavailable':`${Math.floor(s.market_data.feed_age_seconds)}s`}</strong><p>{s?.market_data?.stale?'Latest observation is stale':'Age since last valid quote'}</p></Card>
      <Card title="Last quote event"><strong>{asUtc(eventTime)}</strong><p>Raw: {s?.market_data?.last_raw_event_timestamp??'—'}</p></Card>
      <Card title="Provider messages"><strong>{s?.market_data?.received_messages??'—'}</strong><p>{s?.market_data?.accepted_updates??s?.market_data?.accepted_ticks??0} accepted · {s?.market_data?.rejected_observations??0} rejected</p></Card>
      <Card title="Session"><Status value={s?.market_session?.status}/></Card>
      <Card title="Operator session control">
        {!isOperator&&<p className="muted" style={{margin:'0 0 0.5rem 0',fontSize:'0.85rem'}}>Operator required</p>}
        <div className="actions">
          <button type="button" disabled={sessionBusy||!isOperator} title={!isOperator?'Operator authority required':undefined} onClick={()=>setSession('OPEN')}>Open</button>
          <button type="button" disabled={sessionBusy||!isOperator} title={!isOperator?'Operator authority required':undefined} onClick={()=>setSession('CLOSED')}>Close</button>
        </div>
      </Card>
      <Card title="Tracked stocks"><strong>{symbols.length}</strong></Card>
      <Card title="Accepted / duplicate"><strong>{s?.market_data?.accepted_ticks??'—'} / {s?.market_data?.duplicate_ticks??'—'}</strong></Card>
      <Card title="Late / rejected"><strong>{s?.market_data?.late_ticks??'—'} / {s?.market_data?.rejected_observations??'—'}</strong></Card>
    </div>
    <Card title="Market chart" meta={s?.market_data?.chart_data_status||'UNAVAILABLE'}>
      <CandleChart key={accountId} accountId={accountId} symbol={symbol||undefined} symbols={symbols} candles={s?.candles||[]} formingCandles={forming} latestQuotes={quotes} marketData={s?.market_data||{}} />
    </Card>
    {s?.market_data?.chart_data_reason&&<p className="muted">Chart data status: {s.market_data.chart_data_reason}</p>}
    {s?.market_data?.errors?.length?<Card title="Provider lifecycle errors"><EvidenceView value={s.market_data.errors}/></Card>:null}
    <Card title="Watchlist" meta={`${watchQuotes.length} observed symbols`}><DataTable rows={watchQuotes} columns={[{key:'symbol',label:'Symbol'},{key:'price',label:'Price',render:row=>row.price??'—'},{key:'data_source',label:'Source'},{key:'action',label:'',render:row=><button type="button" onClick={()=>toggleWatch(row.symbol)}>Remove</button>}]}/></Card>
    <Card title="Latest valid quotes" meta={`${displayedQuotes.length} of ${visibleQuotes.length} shown`}>
      <label className="compact-filter">Show stocks<input aria-label="Number of stocks to display" type="number" min="1" max="200" value={displayLimit} onChange={event=>setDisplayLimit(Math.max(1,Math.min(200,Number(event.target.value)||1)))}/></label>
      {displayedQuotes.length?<DataTable rows={displayedQuotes} columns={[{key:'symbol',label:'Symbol'},{key:'provider_symbol',label:'Provider symbol'},{key:'price',label:'Price',render:row=>row.price??'—'},{key:'age_seconds',label:'Age',render:row=>row.age_seconds==null?'—':`${Math.floor(row.age_seconds)}s`},{key:'event_timestamp',label:'Event time',render:row=>asUtc(row.event_timestamp)},{key:'raw_event_timestamp',label:'Raw timestamp',render:row=>row.raw_event_timestamp??'—'},{key:'received_at',label:'Received',render:row=>asUtc(row.received_at)},{key:'volume_available',label:'Volume',render:row=>row.volume_available===false?'Unavailable':'Available'},{key:'data_source',label:'Source'},{key:'watch',label:'',render:row=><button type="button" onClick={()=>toggleWatch(row.symbol)}>{watchlist.includes(row.symbol)?'★':'☆'}</button>}]}/>:<Empty>{s?.market_data?.chart_data_reason||'No valid quote has reached the backend for this provider.'}</Empty>}
    </Card>
    <div className="chart-controls"><label>History timeframe<select value={interval} onChange={event=>setInterval(Number(event.target.value))}><option value={60}>1 minute</option><option value={300}>5 minutes</option></select></label></div>
    <Card title="Forming candles" meta={`${formingRows.length} currently forming`}>
      {formingRows.length?<DataTable rows={formingRows} columns={[{key:'symbol',label:'Symbol'},{key:'interval',label:'Interval (sec)'},{key:'start_time',label:'Bucket start (UTC sec)'},{key:'open',label:'Open'},{key:'high',label:'High'},{key:'low',label:'Low'},{key:'close',label:'Latest'},{key:'data_source',label:'Source'}]}/>:<Empty>{quotes.length?'No forming bar for this selection yet; the latest valid quote remains available above.':'No forming candle because no valid quote has been accepted.'}</Empty>}
    </Card>
    <Card title="Closed candle history" meta={`${historicalRows.length} shown`}>
      <label className="compact-filter">Search stock<input aria-label="Search stock symbols" placeholder="RELIANCE or TCS" value={symbolQuery} onChange={event=>setSymbolQuery(event.target.value)}/></label>
      <label className="compact-filter">Symbol<select aria-label="Filter market data by symbol" value={symbol} onChange={event=>setSymbol(event.target.value)}><option value="">All symbols</option>{filteredSymbols.map(value=><option key={value}>{value}</option>)}</select></label>
      {historyError&&<div className="error" role="status">{historyError}</div>}
      {historyLoading&&!historicalRows.length?<Empty>Loading authenticated candle history…</Empty>:historicalRows.length?<DataTable rows={historicalRows.filter(item=>Number(item.interval)===interval)} columns={[{key:'symbol',label:'Symbol'},{key:'interval',label:'Interval'},{key:'start_time',label:'Bucket start (UTC sec)'},{key:'open',label:'Open'},{key:'high',label:'High'},{key:'low',label:'Low'},{key:'close',label:'Close'},{key:'volume',label:'Volume',render:row=>row.volume_available===false?'Unavailable':String(row.volume??'—')},{key:'data_source',label:'Source'}]}/>:<Empty>{s?.market_data?.chart_data_reason||'No closed candles are available for the active provider.'}</Empty>}
    </Card>
  </Page>
}
function auditEvidence(payload){if(typeof payload!=='string')return payload;try{return JSON.parse(payload)}catch{return payload}}
export function AuditPage(){const {snapshot:s}=useOutletContext();return <Page eyebrow="Durable timeline" title="Audit evidence" description="Monotonic backend events for operational review."><Card title="Recent audit"><DataTable rows={s?.audit} columns={[{key:'sequence',label:'#'},{key:'type',label:'Event'},{key:'recorded_at',label:'Recorded'},{key:'payload',label:'Evidence',render:r=><EvidenceView value={auditEvidence(r.payload)} name="audit evidence"/>}]}/></Card></Page>}
export function NotFoundPage(){return <main className="center"><div><span className="eyebrow">404</span><h1>Route not found</h1><a href="/">Return to overview</a></div></main>}
