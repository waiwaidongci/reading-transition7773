import {domain} from '../constants/domain.js';import {research} from '../stores/research.js';import {session} from '../stores/session.js';import {fragmentsApi} from '../api/research.js';import {sourceOptions} from '../components/common/business.js';import {esc,fmt} from '../utils/format.js';import {action,toast,bind} from '../hooks/actions.js';import {sessionStates} from '../constants/enums.js';

let pendingOps=[];
let pendingSession='';
function stateBadge(s){return '<span class="status '+esc(s)+'">'+esc(sessionStates[s]||s)+'</span>'}
function segText(segments){return segments.map(seg=>seg.map(esc).join(' → ')).join('  ‖  ')}

export async function fragmentsPage(){
  await research.refreshFragments(fragmentsApi);
  if(research.fragmentSession&&!research.fragmentSessions.some(h=>h.session===research.fragmentSession))research.fragmentSession=null;
  const selected=research.fragmentSessions.find(h=>h.session===research.fragmentSession)||null;
  let detail=null;
  if(selected){try{detail=await fragmentsApi.detail(research.sourceId,selected.session)}catch(e){detail=null}}
  const br=research.baseRates||{total_edges:0,base_rate:{},incoming:{}};
  return '<section class="page-heading"><p class="eyebrow">02B / FRAGMENTS &amp; REVISIONS</p><h1>分段、乱序补传的会话，按位置与修订号接续。</h1><p>每个片段带位置与修订号；同版本异值拒收，撤回以墓碑标记。仅位置严格连续的相邻章节连边，缺口两侧不连边。研究只冻结完整已发布版本。</p></section>'
  +'<label class="compact">来源'+esc(domain.source)+'<select id="frag-source-select">'+sourceOptions(research.sources,research.sourceId)+'</select></label>'
  +'<div class="split"><section>'
  +'<h2>片段会话 <small>'+research.fragmentSessions.length+' 个 · 仅已发布会话进入全局计数</small></h2>'
  +(research.fragmentSessions.length?'<div class="table-wrap"><table><thead><tr><th>会话</th><th>状态</th><th>水位/发布修订</th><th>连续段</th><th>缺口</th><th>边数</th><th></th></tr></thead><tbody>'
    +research.fragmentSessions.map(h=>'<tr class="frag-row" data-session="'+esc(h.session)+'" style="cursor:pointer"><td>'+esc(h.session)+'</td><td>'+stateBadge(h.state)+'</td><td>'+h.head_revision+' / '+h.published_revision+'</td><td>'+(h.segment_count??0)+'</td><td>'+(h.gap_count?'<span style="color:var(--accent)">'+h.gap_count+' 处</span>':'无')+'</td><td>'+h.edge_count+'</td><td>'+(h.complete?'✓ 完整':'')+'</td></tr>').join('')
    +'</tbody></table></div>':'<div class="empty">该来源还没有片段会话。在右侧按位置与修订号补传。</div>')
  +(detail?renderDetail(detail):'')
  +'</section><aside class="entry-sheet">'+(session.writable?renderWriter():'<h2>阅读权限</h2><p>可查看全部片段、缺口、边与计数依据；补传与发布由分析师或负责人完成。</p>')
  +'<h2 style="margin-top:26px">全局计数依据</h2><p class="fine">只统计已发布会话的物化边；草稿与缺口不进入。</p><div class="metrics" style="grid-template-columns:1fr 1fr"><div><dt>已发布总边数</dt><dd>'+fmt(br.total_edges)+'</dd></div><div><dt>到达章节数</dt><dd>'+Object.keys(br.base_rate).length+'</dd></div></div>'
  +(Object.keys(br.base_rate).length?'<div class="table-wrap"><table><thead><tr><th>目标章节</th><th>到达次数</th><th>基率</th></tr></thead><tbody>'+Object.entries(br.base_rate).sort((a,b)=>b[1]-a[1]).map(([k,v])=>'<tr><td>'+esc(k)+'</td><td>'+fmt(br.incoming[k])+'</td><td>'+fmt(v)+'</td></tr>').join('')+'</tbody></table></div>':'<p class="fine">暂无已发布边。</p>')
  +'<p class="fine" style="margin-top:18px">旧整行样本（阅读文集页）与已批准建议仍可读取，并与完整已发布片段会话一并纳入研究。</p>'
  +'</aside></div>';
}
function renderDetail(d){
  return '<h2 style="margin-top:30px">会话 '+esc(d.session)+' 的片段与接缝</h2>'
  +'<p class="fine">水位 rev='+d.head_revision+' · 已发布 rev='+d.published_revision+' · 重建 rev='+d.rebuilt_revision+' · 状态 '+esc(sessionStates[d.state]||d.state)+(d.complete?' · 完整可冻结':'')+'</p>'
  +'<h2>有效连续段 <small>缺口处分段</small></h2><p>'+(d.segments.length?segText(d.segments):'<span class="fine">无有效片段</span>')+'</p>'
  +(d.gaps.length?'<div class="failure" style="padding:14px"><strong>位置缺口（两侧不连边）：</strong><ul style="margin:6px 0 0">'+d.gaps.map(g=>'<li>位置 '+g.after_position+' 之后缺失 '+g.missing_from+(g.missing_to>g.missing_from?('–'+g.missing_to):'')+'</li>').join('')+'</ul></div>':'<p class="fine">无缺口，位置连续。</p>')
  +'<h2>物化相邻边 <small>仅连续位置</small></h2>'+(d.edges.length?'<div class="table-wrap"><table><thead><tr><th>位置</th><th>当前章</th><th>下一章节</th><th>依据修订</th></tr></thead><tbody>'+d.edges.map(e=>'<tr><td>'+e.position+'</td><td>'+esc(e.from)+'</td><td>'+esc(e.to)+'</td><td>rev'+e.built_revision+'</td></tr>').join('')+'</tbody></table></div>':'<p class="fine">没有相邻边（单章或全部为缺口）。</p>')
  +'<h2>片段流水 <small>同位置取最高有效修订；墓碑=撤回</small></h2><div class="table-wrap"><table><thead><tr><th>位置</th><th>修订</th><th>章节</th><th>状态</th><th>来源引用</th></tr></thead><tbody>'
  +d.fragments.map(f=>'<tr><td>'+f.position+'</td><td>rev'+f.revision+'</td><td>'+(f.chapter?esc(f.chapter):'<span class="fine">—</span>')+'</td><td>'+(f.tombstone?'<span style="color:var(--accent)">已撤回</span>':'有效')+'</td><td class="fine">'+esc(f.client_ref||'')+'</td></tr>').join('')
  +'</tbody></table></div>'
  +(session.writable?'<div style="margin-top:14px"><button id="publish-session" class="secondary" '+(d.state==='published'&&d.published_revision===d.head_revision?'disabled':'')+'>发布当前有效版本 →</button> <span class="fine">发布后该完整会话才进入研究与全局基率</span></div>':'');
}
function renderWriter(){
  const sessionValue=pendingSession||research.fragmentSession||'';
  return '<h2>补传 / 撤回片段</h2>'
  +'<form id="frag-op-form"><label>会话编号<input name="session_key" required placeholder="SY-F-001" value="'+esc(sessionValue)+'"></label>'
  +'<div class="parameter-fields"><label>位置 position（从0开始）<input name="position" type="number" min="0" required value="0"></label><label>修订号 revision（≥1）<input name="revision" type="number" min="1" required value="1"></label></div>'
  +'<label>章节 chapter（撤回时留空）<input name="chapter" placeholder="序章"></label>'
  +'<label style="display:flex;align-items:center;gap:8px;font-weight:400"><input type="checkbox" name="tombstone" style="width:auto"> 撤回该位置（墓碑）</label>'
  +'<button type="submit" class="secondary">加入本批</button></form>'
  +'<h2 style="margin-top:20px">本批操作 <small>'+pendingOps.length+' 条</small></h2>'
  +(pendingOps.length?'<div class="table-wrap"><table><thead><tr><th>位置</th><th>修订</th><th>章节</th><th></th></tr></thead><tbody>'
    +pendingOps.map((o,i)=>'<tr><td>'+o.position+'</td><td>rev'+o.revision+'</td><td>'+(o.tombstone?'<span style="color:var(--accent)">撤回</span>':esc(o.chapter||''))+'</td><td><button type="button" class="secondary remove-op" data-i="'+i+'">移除</button></td></tr>').join('')+'</tbody></table></div>':'<p class="fine">尚未加入操作。可乱序、可同修订多位置。</p>')
  +'<form id="frag-submit-form" style="margin-top:14px"><label>幂等键 idempotency_key（可选，重试不重复计数）<input name="idempotency_key" placeholder="uuid-..."></label><button type="submit">提交本批片段 →</button></form>'
  +'<details style="margin-top:18px"><summary>JSON 批量 / 乱序补传</summary><form id="frag-json-form"><label style="margin-top:12px"><textarea name="json" rows="6" placeholder=\'[{"position":0,"revision":1,"chapter":"序章"},{"position":2,"revision":2,"tombstone":true}]\'></textarea></label><button type="submit" class="secondary">解析并替换本批</button></form></details>';
}
export function bindFragments(refresh){
  bind('#frag-source-select','change',async e=>{research.sourceId=Number(e.target.value);research.fragmentSession=null;pendingOps=[];pendingSession='';await refresh()});
  bind('#frag-op-form [name=session_key]','input',e=>{pendingSession=e.target.value});
  document.querySelectorAll('.frag-row').forEach(tr=>tr.addEventListener('click',()=>{research.fragmentSession=tr.dataset.session;pendingSession=tr.dataset.session;refresh()}));
  bind('#publish-session','click',async()=>{try{await fragmentsApi.publish(research.sourceId,research.fragmentSession);toast('已发布当前有效版本');await refresh()}catch(e){toast(e.message,true)}});
  action('#frag-op-form',async form=>{
    const f=new FormData(form);const tombstone=f.get('tombstone')==='on';
    const op={position:Number(f.get('position')),revision:Number(f.get('revision')),tombstone};
    if(!tombstone){const ch=(f.get('chapter')||'').trim();if(!ch){toast('非撤回操作必须填写章节',true);return}op.chapter=ch}
    if(pendingOps.some(o=>o.position===op.position&&o.revision===op.revision)){toast('本批已存在相同位置/修订',true);return}
    pendingOps.push(op);await refresh()
  });
  document.querySelectorAll('.remove-op').forEach(b=>b.addEventListener('click',()=>{pendingOps.splice(Number(b.dataset.i),1);refresh()}));
  action('#frag-submit-form',async form=>{
    const keyForm=new FormData(form);const sessionInput=document.querySelector('#frag-op-form [name=session_key]');
    const sessionKey=(sessionInput?.value||'').trim();
    if(!sessionKey){toast('请先填写会话编号',true);return}
    if(!pendingOps.length){toast('本批没有操作',true);return}
    const payload={session:sessionKey,operations:pendingOps.map(o=>({...o}))};
    const idem=(keyForm.get('idempotency_key')||'').trim();if(idem)payload.idempotency_key=idem;
    const r=await fragmentsApi.ingest(research.sourceId,payload);
    pendingOps=[];pendingSession='';research.fragmentSession=sessionKey;toast(r.replayed?'幂等重放，未重复计数':'已接收 rev'+r.head_revision+'，重建已排队');await refresh()
  });
  action('#frag-json-form',async form=>{
    const f=new FormData(form);let ops;
    try{ops=JSON.parse(f.get('json'))}catch{toast('JSON 解析失败',true);return}
    if(!Array.isArray(ops)||!ops.length){toast('需要非空数组',true);return}
    pendingOps=ops.map(o=>({position:Number(o.position),revision:Number(o.revision),chapter:o.tombstone?undefined:String(o.chapter),tombstone:!!o.tombstone}));
    toast('已载入 '+pendingOps.length+' 条操作');await refresh()
  });
}
