/* ===== Loop Platform JS ===== */
/* 登录 */
function fillDemo(){document.getElementById('loginUser').value='admin';document.getElementById('loginPass').value='loop123';}
function doLogin(){
  var u=document.getElementById('loginUser').value.trim(),p=document.getElementById('loginPass').value.trim();
  if(u==='admin'&&p==='loop123'){document.getElementById('loginMask').classList.add('hide');}
  else{document.getElementById('loginErr').style.display='block';}
}
function logout(){document.getElementById('loginMask').classList.remove('hide');}

/* 导航 */
function go(el){
  document.querySelectorAll('.nav-item').forEach(function(n){n.classList.remove('active');});
  el.classList.add('active');
  var page=el.getAttribute('data-page');
  document.querySelectorAll('.page').forEach(function(p){p.classList.remove('active');});
  var target=document.getElementById('page-'+page);if(target)target.classList.add('active');
  var crumb=document.getElementById('crumbCur');if(crumb)crumb.textContent=el.getAttribute('data-title');
  var main=document.getElementById('main');if(main)main.scrollTop=0;
  closeDrawer();onPageEnter(page);
  try{localStorage.setItem('loop-page',page);}catch(e){}
}
function toggleNav(){document.getElementById('app').classList.toggle('collapsed');}
function toggleTheme(){var d=document.documentElement.classList.toggle('dark');try{localStorage.setItem('loop-theme',d?'dark':'light');}catch(e){}}
try{if(localStorage.getItem('loop-theme')==='dark')document.documentElement.classList.add('dark');}catch(e){}
var toastTimer;
function toast(msg){var t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(function(){t.classList.remove('show');},2200);}

/* 模态框 */
function openModal(id){document.getElementById(id).classList.add('open');}
function closeModal(id){document.getElementById(id).classList.remove('open');}
function reqTab(btn,which){
  btn.parentNode.querySelectorAll('button').forEach(function(b){b.classList.remove('active');});btn.classList.add('active');
  document.getElementById('reqtab-txt').style.display=which==='txt'?'block':'none';
  document.getElementById('reqtab-fs').style.display=which==='fs'?'block':'none';
}
function parseFs(v){
  var pv=document.getElementById('fsPreview');v=v.trim();if(!v){pv.style.display='none';return;}
  var m=v.match(/(wiki|docx|docs)\/([A-Za-z0-9]+)/),kind='wiki_token',token='';
  if(m){kind=m[1]==='wiki'?'wiki_token':'doc_token';token=m[2];}else if(!v.includes('/')){token=v;}
  pv.style.display='block';
  if(token){pv.innerHTML='解析成功：<b>'+kind+'</b> = '+token.slice(0,18)+'...';}
  else{pv.innerHTML='无法解析，请粘贴 wiki / docx 链接';}
}

/* Harness 筛选 */
function filterHarness(btn,level){
  btn.parentNode.querySelectorAll('button').forEach(function(b){b.classList.remove('active');});btn.classList.add('active');
  document.querySelectorAll('#harnessList .file-row').forEach(function(r){r.style.display=(level==='all'||r.getAttribute('data-level')===level)?'flex':'none';});
}

/* Harness 抽屉 */
function openConstraint(name,level,quad,path){
  document.getElementById('dwName').textContent=name;document.getElementById('dwPath').textContent=path;
  document.getElementById('dwQuad').textContent=quad;
  var lv=document.getElementById('dwLevel');lv.textContent=level==='system'?'系统级':'项目级';
  lv.className='badge '+(level==='system'?'gray':'purple');
  var code='# '+name+'\n\n文件内容将通过 API 加载';
  document.getElementById('dwCode').textContent=code;document.getElementById('dwEdit').value=code;
  cancelEdit();document.getElementById('drawer').classList.add('open');
}
function closeDrawer(){document.getElementById('drawer').classList.remove('open');}
function editConstraint(){document.getElementById('dwView').style.display='none';document.getElementById('dwEdit').style.display='block';}
function cancelEdit(){document.getElementById('dwView').style.display='block';document.getElementById('dwEdit').style.display='none';}
function saveConstraint(){document.getElementById('dwCode').textContent=document.getElementById('dwEdit').value;cancelEdit();toast('已保存');}

/* 设置 */
function setTab(el,which){
  el.parentNode.querySelectorAll('.set-tab').forEach(function(t){t.classList.remove('active');});el.classList.add('active');
  document.querySelectorAll('.set-panel').forEach(function(p){p.classList.remove('active');});
  var panel=document.getElementById('set-'+which);if(panel)panel.classList.add('active');
}
function openDeploy(kind){
  document.getElementById('dpTitle').textContent='添加部署渠道 · '+kind;
  var b=document.getElementById('dpBody'),h='';
  if(kind==='GitHub'){h='<div class="form-row"><label>仓库 URL</label><input id="deploy_remote" placeholder="github.com/owner/repo.git"></div>';}
  else if(kind==='ECS'){h='<div class="form-grid"><div class="form-row"><label>IP</label><input id="deploy_host"></div><div class="form-row"><label>用户</label><input id="deploy_user" value="root"></div></div>';}
  else{h='<div class="form-row"><label>分发 ID</label><input placeholder="E1XXXXXXXXXXXX"></div>';}
  b.innerHTML=h;openModal('deployModal');
}
function saveDeployChannel(){
  var data={};var el;el=document.getElementById('deploy_remote');if(el&&el.value)data['HARNESS_GIT_REMOTE']=el.value;
  el=document.getElementById('deploy_host');if(el&&el.value)data['ECS_HOST']=el.value;
  el=document.getElementById('deploy_user');if(el&&el.value)data['ECS_SSH_USER']=el.value;
  if(Object.keys(data).length===0){toast('请填写至少一个字段');return;}
  apiPost('/api/config',data).then(function(r){closeModal('deployModal');toast(r.ok?'已保存':'保存失败');});
}
function openMaker(type){
  document.getElementById('mkTitle').textContent='添加 Maker · '+(type==='api'?'API型':'CLI Agent型');
  var b=document.getElementById('mkBody'),h='<div class="form-row"><label>名称</label><input id="maker_name" placeholder="如 DeepSeek"></div>';
  if(type==='api'){h+='<div class="form-row"><label>模型</label><input id="maker_model" placeholder="deepseek-chat"></div>';}
  else{h+='<div class="form-row"><label>命令</label><input id="maker_cmd" placeholder="claude -p {prompt}"></div>';}
  b.innerHTML=h;openModal('makerModal');
}
function saveMakerProfile(){
  var name=(document.getElementById('maker_name')||{}).value;if(!name||!name.trim()){toast('请输入名称');return;}
  var data={maker_name:name.trim()};
  var el;el=document.getElementById('maker_model');if(el&&el.value)data['maker_model']=el.value;
  el=document.getElementById('maker_cmd');if(el&&el.value)data['maker_cmd']=el.value;
  apiPost('/api/config',data).then(function(r){closeModal('makerModal');toast(r.ok?'已保存':'保存失败');});
}

/* Loop Graph */
var LICON={
  req:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><line x1="9" y1="6" x2="20" y2="6"/><circle cx="4.5" cy="6" r="1.4"/></svg>',
  mk:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M12 3v3M5 8l2 2M19 8l-2 2M4 15h16M6 15l1.5 5h9L18 15"/></svg>',
  ck:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M9 11l3 3 8-8"/></svg>',
  pub:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M12 3c3 1 5 4 5 8"/></svg>',
  arrow:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><path d="M5 12h14M13 6l6 6-6 6"/></svg>'
};
function lgNodes(st){
  var defs=[{k:'req',nm:'取需求',sub:'backlog',ic:LICON.req},{k:'mk',nm:'Maker',sub:'生成',ic:LICON.mk},{k:'ck',nm:'Checker',sub:'验收',ic:LICON.ck},{k:'pub',nm:'发布',sub:'部署',ic:LICON.pub}];
  var h='<div class="lg-nodes">';
  defs.forEach(function(d,i){if(i>0)h+='<div class="lg-arrow">'+LICON.arrow+'</div>';h+='<div class="lg-node '+(st[d.k]||'')+'"><div class="lg-ico">'+d.ic+'</div><div class="lg-nm">'+d.nm+'</div></div>';});
  h+='</div>';return h;
}
function renderGraph(id,st){var el=document.getElementById(id);if(!el)return;el.innerHTML=lgNodes(st||{});}
function lpTab(el,which){
  el.parentNode.querySelectorAll('.lp-tab').forEach(function(t){t.classList.remove('active');});el.classList.add('active');
  document.getElementById('lpv-console').classList.toggle('active',which==='console');
  document.getElementById('lpv-replay').classList.toggle('active',which==='replay');
}
var lpRunning=false;
function setRunState(cls,txt){var s=document.getElementById('runState');s.className='run-state '+cls;s.innerHTML='<span class="dot"></span>'+txt;}
function lpRun(){
  if(!API_LIVE){toast('未连后端');return;}
  return lpRunReal();
}
function onPageEnter(page){
  if(page==='harness')loadConstraints(false);
  else if(page==='dashboard')loadDashboard();
  else if(page==='reqs')loadReqs();
  else if(page==='monitor')loadMonitor();
  else if(page==='loop'){loadTrigReqs();loadPipeline();loadChecks();}
  else if(page==='apps')loadApps();
  else if(page==='setting'){loadSettings();}
}

/* ===== API Layer ===== */
var API_BASE='';var API_LIVE=false;
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
async function apiGet(path){var r=await fetch(API_BASE+path);if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}
async function apiPost(path,body){var r=await fetch(API_BASE+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});var j=await r.json().catch(function(){return{};});return{status:r.status,ok:r.ok,json:j};}
async function probeLive(manual){
  try{await apiGet('/api/config');API_LIVE=true;}catch(e){API_LIVE=false;}
  if(manual)toast(API_LIVE?'已连接后端':'未连接后端');
  return API_LIVE;
}

/* Dashboard */
async function loadDashboard(){
  try{var d=await apiGet('/api/backlog');var items=d.docs||[];
    var done=items.filter(function(x){return x.status==='done';}).length;
    var failed=items.filter(function(x){return x.status==='failed';}).length;
    var pending=items.filter(function(x){return x.pending;}).length;
    document.getElementById('kpiTotal').textContent=items.length;
    document.getElementById('kpiDone').textContent=done;
  }catch(e){}
  try{
    var t=await apiGet('/api/trace?limit=5');
    var events=(t.events||[]).filter(function(e){return e.event==='case_done';});
    var h='';
    events.reverse().forEach(function(r){
      h+='<tr><td>'+esc(r._ts||'')+'</td><td>'+esc(r.case||'')+'</td><td>'+(r.result==='pass'?'<span class="badge green">PASS</span>':'<span class="badge red">FAIL</span>')+'</td><td>'+(r.attempts||'?')+'</td><td>'+(r.determinism||'skip')+'</td></tr>';
    });
    if(!h)h='<tr><td colspan="5" class="hint">暂无运行记录</td></tr>';
    document.getElementById('dashRuns').innerHTML=h;
  }catch(e){}
}

/* 需求列表 */
async function loadReqs(){
  try{var d=await apiGet('/api/backlog');var items=d.docs||[];var h='';
    items.forEach(function(x){
      h+='<div class="card" style="margin-bottom:8px"><div style="display:flex;justify-content:space-between;align-items:center"><div><b>'+esc(x.id)+'</b> '+esc(x.title)+'</div><div><span class="badge '+(x.status==='done'?'green':x.status==='failed'?'red':'orange')+'">'+esc(x.status||'pending')+'</span></div></div></div>';
    });
    document.getElementById('reqList').innerHTML=h||'<div class="hint">暂无需求，点右上添加</div>';
  }catch(e){}
}

/* 监控 */
async function loadMonitor(){
  var runsEl=document.getElementById('monitorRuns');if(!runsEl)return;
  try{
    var t=await apiGet('/api/trace?limit=50');var m=t.metrics||{};var events=t.events||[];
    var h='';
    if(m.total_cases){h='<div class="grid g3" style="margin-bottom:12px">'
      +'<div class="card"><div class="stat-num">'+m.total_cases+'</div><div class="stat-label">总用例</div></div>'
      +'<div class="card"><div class="stat-num">'+m.pass_rate+'%</div><div class="stat-label">通过率</div></div>'
      +'<div class="card"><div class="stat-num">'+m.first_pass_rate+'%</div><div class="stat-label">一次通过率</div></div></div>'
      +'<div class="grid g3"><div class="card"><div class="stat-num">'+m.total_cost_yuan+'</div><div class="stat-label">累计花费</div></div>'
      +'<div class="card"><div class="stat-num">'+m.avg_attempts+'</div><div class="stat-label">平均尝试</div></div>'
      +'<div class="card"><div class="stat-num">'+m.total_batches+'</div><div class="stat-label">批次数</div></div></div>';}
    else{h='<p class="hint">暂无数据，执行一次交付后显示</p>';}
    runsEl.innerHTML=h;
    var logEl=document.getElementById('monitorLog');if(logEl&&events.length){
      var eh='';events.slice(-10).reverse().forEach(function(e){eh+='<div style="font-size:12px;color:var(--muted)">['+(e._ts||'')+'] '+e.event+(e.case?' '+e.case:'')+'</div>';});
      logEl.innerHTML=eh;
    }
  }catch(e){runsEl.innerHTML='<p class="hint">未连后端</p>';}
}

/* APP List */
async function loadApps(){
  var grid=document.getElementById('appsGrid');if(!grid)return;
  try{var d=await apiGet('/api/apps');var apps=d.apps||[];
    grid.innerHTML=apps.map(function(a){return'<div class="card"><b>'+esc(a.title)+'</b> <span class="badge '+(a.online?'green':'red')+'">'+(a.online?'在线':'离线')+'</span><div class="hint">'+esc(a.url)+'</div></div>';}).join('')||'<div class="hint">暂无已部署应用</div>';}
  catch(e){}
}

/* Loop 引擎 */
async function loadTrigReqs(){
  try{var d=await apiGet('/api/backlog');var items=d.docs||[];var sel=document.getElementById('trigReq');
    if(sel){sel.innerHTML='<option value="">整池</option>'+items.filter(function(x){return x.pending;}).map(function(x){return'<option value="'+esc(x.id)+'">'+esc(x.id)+' '+esc(x.title)+'</option>';}).join('');}
  }catch(e){}
  renderGraph('lgConsole',{req:'run'});
}
function step(id,icon,txt,detail){
  var el=document.getElementById(id);if(!el)return;
  el.querySelector('.cl-icon').textContent=icon;
  el.querySelector('.cl-detail').innerHTML=txt+(detail?' <span class="hint">'+detail+'</span>':'');
}
/* 流程全景：拉取 /api/pipeline，按环节分组展示每个子步骤 */
async function loadPipeline(){
  var box=document.getElementById('pipelinePanorama');if(!box)return;
  try{
    var d=await apiGet('/api/pipeline');
    if(!d.ok){box.innerHTML='<span class="hint">加载失败：'+esc(d.error||'')+'</span>';return;}
    var stages=d.stages||[];
    var stat=document.getElementById('pipeStat');
    if(stat){var n=0;stages.forEach(function(s){n+=(s.items||[]).length;});stat.textContent='共 '+stages.length+' 个环节 · '+n+' 项';}
    var html='';
    stages.forEach(function(s){
      var items=s.items||[];
      html+='<div style="margin:14px 0 6px;font-weight:700;font-size:13px">'+(s.icon||'•')+' '+esc(s.name)
           +' <span class="badge blue">'+items.length+'</span>';
      if(s.desc)html+=' <span class="hint" style="font-weight:400">'+esc(s.desc)+'</span>';
      html+='</div>';
      items.forEach(function(it){
        var icon,tag='';
        var iid='pipe-'+s.key+'-'+String(it.id||'').replace(/[^a-z0-9]/gi,'_');
        if(s.key==='features'){
          icon=it.on?'✅':'⬜';
          tag=it.on?'<span class="badge green">已开启</span>':'<span class="badge gray">已关闭</span>';
          html+='<div class="cl-item" id="'+iid+'" style="cursor:pointer" title="点击切换" onclick="toggleFeature(\''+esc(it.id)+'\','+(it.on?'true':'false')+')">'
               +'<span class="cl-icon">'+icon+'</span>'
               +'<span class="cl-label"><span class="badge gray">'+esc(it.id||'')+'</span> '+esc(it.name)+' '+tag+'</span>'
               +'<span class="cl-detail hint">点击切换 ⇄</span>'
               +'</div>';
        }else{
          icon='🔹';
          html+='<div class="cl-item" id="'+iid+'">'
               +'<span class="cl-icon">'+icon+'</span>'
               +'<span class="cl-label"><span class="badge gray">'+esc(it.id||'')+'</span> '+esc(it.name)+' '+tag+'</span>'
               +'<span class="cl-detail hint">'+esc(it.desc||'')+'</span>'
               +'</div>';
        }
      });
    });
    box.innerHTML=html||'<span class="hint">无环节</span>';
  }catch(e){box.innerHTML='<span class="hint">加载失败：'+esc(e.message)+'</span>';}
}
/* 点击切换功能开关（落到 /api/features），成功后刷新流程全景 */
async function toggleFeature(key,curOn){
  if(!API_LIVE){toast('未连后端');return;}
  var body={};body[key]=!curOn;
  try{
    var r=await apiPost('/api/features',body);
    if(r.ok&&r.json&&r.json.ok){toast((!curOn?'已开启 ':'已关闭 ')+key);loadPipeline();}
    else{toast('切换失败');}
  }catch(e){toast('切换失败：'+e.message);}
}
/* ===== 流程运行联动：真实触发 gate/generate，根据真实日志高亮对应环节（不造假） ===== */
var PIPE_MARKERS={
  gate:[{id:'1/3',re:/门禁\s*1\/3/},{id:'2/3',re:/门禁\s*2\/3/},{id:'3/3',re:/门禁\s*3\/3/}],
  generate:[{id:'S1',re:/第\s*\d+\s*次生成/},{id:'S5',re:/确定性复跑/},{id:'S6',re:/runs\.jsonl|全部回归用例通过/}],
  mumuspec:[{id:'R1',re:/\bR1\b/},{id:'R2',re:/\bR2\b/},{id:'R3',re:/\bR3\b/},{id:'R4',re:/\bR4\b/},{id:'R5',re:/\bR5\b/},{id:'R6',re:/\bR6\b/}]
};
function pipeSetIcon(groupKey,itemId,icon){
  var el=document.getElementById('pipe-'+groupKey+'-'+String(itemId).replace(/[^a-z0-9]/gi,'_'));
  if(el){var ic=el.querySelector('.cl-icon');if(ic)ic.textContent=icon;}
}
function pipeResetGroups(keys){
  keys.forEach(function(g){(PIPE_MARKERS[g]||[]).forEach(function(m){pipeSetIcon(g,m.id,'🔹');});});
}
/* 根据日志高亮某组：命中的最后一个标记=当前(运行中🔄、已结束✅)，之前的=✅ */
function pipeApply(groupKey,log,finished){
  var markers=PIPE_MARKERS[groupKey]||[];var lastHit=-1;
  markers.forEach(function(m,idx){if(m.re.test(log))lastHit=idx;});
  if(lastHit<0)return false;
  markers.forEach(function(m,idx){
    if(idx<lastHit)pipeSetIcon(groupKey,m.id,'✅');
    else if(idx===lastHit)pipeSetIcon(groupKey,m.id,finished?'✅':'🔄');
  });
  return true;
}
var _pipePoll=null;
function pipeSetBusy(busy,label){
  var g=document.getElementById('pipeGateBtn'),n=document.getElementById('pipeGenBtn');
  if(g)g.disabled=busy;if(n)n.disabled=busy;
  var st=document.getElementById('pipeRunState');if(st)st.textContent=label||'';
}
async function runGate(){
  if(!API_LIVE){toast('未连后端');return;}
  var r=await apiPost('/api/gate',{});
  if(r.status===409){toast('门禁正在运行');return;}
  if(!r.ok){toast('启动失败');return;}
  pipeResetGroups(['gate','generate']);toast('门禁已启动');
  pollEngine('gate',['gate','generate']);
}
async function runGenerate(){
  if(!API_LIVE){toast('未连后端');return;}
  var r=await apiPost('/api/generate',{});
  if(r.status===409){toast('生成正在运行');return;}
  if(!r.ok){toast('启动失败');return;}
  pipeResetGroups(['generate']);toast('生成已启动');
  pollEngine('generate',['generate']);
}
/* 轮询引擎真实状态，把日志套到各相关组上高亮 */
function pollEngine(key,groups){
  if(_pipePoll)clearInterval(_pipePoll);
  pipeSetBusy(true,'● '+key+' 运行中');
  var url='/api/'+key+'/status';
  _pipePoll=setInterval(async function(){
    try{
      var s=await apiGet(url);var log=s.log||'';var finished=(s.exit_code!==null&&s.exit_code!==undefined&&!s.running);
      groups.forEach(function(g){pipeApply(g,log,finished);});
      if(finished){
        clearInterval(_pipePoll);_pipePoll=null;
        var ok=s.exit_code===0;
        pipeSetBusy(false,(ok?'✅ ':'❌ ')+key+(ok?' 完成':' 失败(exit '+s.exit_code+')'));
        toast(key+(ok?' 完成':' 失败'));
      }
    }catch(e){clearInterval(_pipePoll);_pipePoll=null;pipeSetBusy(false,'⚠ 轮询中断');}
  },1500);
}
/* 检查项全景：拉取 /api/checks，按四象限(环节)分组展示每个 checker */
var QUAD_META={
  'inject-rule':{nm:'前馈 · 注入规则',badge:'blue',ic:'📝'},
  'inject-infer':{nm:'前馈 · 推理注入',badge:'purple',ic:'🧠'},
  'check-rule':{nm:'后馈 · 计算检查',badge:'green',ic:'✅'},
  'check-infer':{nm:'后馈 · 推理判定',badge:'gray',ic:'⚖️'}
};
var QUAD_ORDER=['inject-rule','inject-infer','check-rule','check-infer'];
async function loadChecks(){
  var box=document.getElementById('checkPanorama');if(!box)return;
  try{
    var d=await apiGet('/api/checks');
    if(!d.ok){box.innerHTML='<span class="hint">加载失败：'+esc(d.error||'')+'</span>';return;}
    var checks=d.checks||[];
    var stat=document.getElementById('checksStat');
    if(stat&&d.summary){stat.textContent='共 '+d.summary.total+' 项 · 自动 '+d.summary.auto+' · Mock '+d.summary.mocked;}
    var groups={};checks.forEach(function(c){(groups[c.quadrant]=groups[c.quadrant]||[]).push(c);});
    var html='';
    QUAD_ORDER.forEach(function(q){
      var list=groups[q];if(!list||!list.length)return;
      var m=QUAD_META[q]||{nm:q,badge:'gray',ic:'•'};
      html+='<div style="margin:14px 0 6px;font-weight:700;font-size:13px">'+m.ic+' '+m.nm
           +' <span class="badge '+m.badge+'">'+list.length+'</span></div>';
      list.forEach(function(c){
        var icon=!c.active?'⬜':(c.mock?'🧪':'✅');
        var tag=!c.active?'<span class="badge gray">未生效</span>':(c.mock?'<span class="badge purple">Mock</span>':'<span class="badge green">自动</span>');
        html+='<div class="cl-item" id="chk-'+esc(c.id)+'">'
             +'<span class="cl-icon">'+icon+'</span>'
             +'<span class="cl-label">'+esc(c.name)+' '+tag
             +' <span class="badge blue">'+esc(c.category||'-')+'</span>'
             +' <span class="chk-run"></span></span>'
             +'<span class="cl-detail hint">'+esc(c.description||'')+'</span>'
             +'</div>';
      });
    });
    box.innerHTML=html||'<span class="hint">无检查项</span>';
  }catch(e){box.innerHTML='<span class="hint">加载失败：'+esc(e.message)+'</span>';}
}
/* 运行时把真实跑过的可执行 checker(security/runtime/e2e)结果回填到「检查项全景」对应目录项。
   映射依据(保守、不硬凑):security→FB-C-02(扫危险调用) / runtime→FB-C-06(http_status);
   e2e 为 DOM 级检查,目录无对应原语,结果仅见「交付流程」7 步,不在此伪造。 */
var RUN_TO_CHECKS={security:['FB-C-02'],runtime:['FB-C-06'],e2e:[]};
function panoResetRun(){
  document.querySelectorAll('.chk-run').forEach(function(s){s.textContent='';s.className='chk-run';});
}
function panoMarkRun(name,ok,detail){
  (RUN_TO_CHECKS[name]||[]).forEach(function(id){
    var el=document.getElementById('chk-'+id);if(!el)return;
    var badge=el.querySelector('.chk-run');if(!badge)return;
    badge.textContent=ok?'本次 ✓':'本次 ✗ '+String(detail||'').slice(0,40);
    badge.className='chk-run badge '+(ok?'green':'red');
  });
}
async function lpRunReal(){
  if(lpRunning)return;lpRunning=true;
  var btn=document.getElementById('trigBtn');btn.disabled=true;
  setRunState('running','运行中');
  var log=document.getElementById('liveLog');log.textContent='';
  // 重置清单
  ['cl-fetch','cl-generate','cl-security','cl-runtime','cl-e2e','cl-publish','cl-deploy'].forEach(function(id){step(id,'⬜','');});
  panoResetRun();
  var _crn=document.getElementById('checksRunNote');
  if(_crn)_crn.textContent='本次运行回填:security→FB-C-02 / runtime→FB-C-06(e2e 无对应目录项)';

  // 1. 获取需求
  var taskId_sel=document.getElementById('trigReq')?document.getElementById('trigReq').value:'';
  var makerEl=document.getElementById('trigMaker');var maker=makerEl?makerEl.value||'deepseek':'deepseek';
  var prompt='';
  if(taskId_sel){
    log.textContent+='[1/7] 获取需求: '+taskId_sel+'\n';
    try{
      var bl=await apiGet('/api/backlog');
      var item=(bl.docs||[]).find(function(d){return d.id===taskId_sel;});
      if(item&&item.spec_text){
        prompt=item.spec_text+'\n\n你是代码生成器。根据需求生成完整应用，自由选择技术栈。\n\n===== 工程结构(强制) =====\n按工程化结构拆分多个文件:HTML/CSS/JS 分离，页面多于一个时拆成多个页面文件；禁止把所有代码塞进单个 index.html。\n\n===== 部署脚本(强制) =====\n必须包含 deploy.sh:安装依赖并后台启动服务，启动方式由你根据所选技术栈决定，但必须遵守契约:\n1) 服务读 PORT 环境变量、监听 0.0.0.0；\n2) 后台启动并落盘进程号与日志，末尾必须类似:setsid nohup <启动命令> > app.log 2>&1 & 且 echo $! > app.pid；\n3) 只能用服务器已有运行时(python3/pip3；纯静态可用 python3 -m http.server "$PORT" --bind 0.0.0.0)。\n\n===== 输出格式(强制) =====\n只输出文件，不要任何解释、不要 markdown 代码围栏(```)。每个文件用如下格式:\n<<<FILE: 相对路径>>>\n文件内容\n<<<ENDFILE>>>';
        log.textContent+='需求: '+item.spec_text.substring(0,200)+'...\\n';
        step('cl-fetch','✅',item.title);
      }else{
        log.textContent+='⚠️ 该任务无需求文本\\n';
        step('cl-fetch','⚠️','无需求文本');
      }
    }catch(e){step('cl-fetch','❌','获取失败');}
  }
  if(!prompt){step('cl-fetch','⬜','整池模式');prompt='你是代码生成器。生成一个完整的Web应用。自由选择技术栈。\n\n===== 工程结构(强制) =====\n按工程化结构拆分多个文件:HTML/CSS/JS 分离，页面多于一个时拆成多个页面文件；禁止把所有代码塞进单个 index.html。\n\n===== 部署脚本(强制) =====\n必须包含 deploy.sh:安装依赖并后台启动服务，启动方式由你根据所选技术栈决定，但必须遵守契约:\n1) 服务读 PORT 环境变量、监听 0.0.0.0；\n2) 后台启动并落盘进程号与日志，末尾必须类似:setsid nohup <启动命令> > app.log 2>&1 & 且 echo $! > app.pid；\n3) 只能用服务器已有运行时(python3/pip3；纯静态可用 python3 -m http.server "$PORT" --bind 0.0.0.0)。\n\n===== 输出格式(强制) =====\n只输出文件，不要任何解释、不要 markdown 代码围栏(```)。每个文件用如下格式:\n<<<FILE: 相对路径>>>\n文件内容\n<<<ENDFILE>>>';}

  // 2. 生成代码
  log.textContent+='[2/7] 生成代码...\\n';
  var r=await apiPost('/api/maker/run',{prompt:prompt,maker:maker});
  if(!r.json||!r.json.ok){step('cl-generate','❌','启动失败');lpRunning=false;btn.disabled=false;setRunState('fail','失败');return;}
  var taskId=r.json.task_id;
  for(var poll=0;poll<200;poll++){
    await new Promise(function(r){setTimeout(r,3000);});
    try{
      var s=await apiGet('/api/maker/status?task='+taskId);
      if(s.status==='failed'){step('cl-generate','❌',s.error||'生成失败');log.textContent+='❌ 生成失败: '+(s.error||'')+'\\n';break;}
      if(s.status==='done'){
        step('cl-generate','✅',(s.files||[]).length+' 文件, ¥'+(s.cost_yuan||0));
        log.textContent+='✅ 生成完成 ('+(s.files||[]).length+' 文件, ¥'+(s.cost_yuan||0)+')\\n';
        var links='';
        var fs=s.files||[];
        for(var fi=0;fi<fs.length;fi++){
          var furl=s.output_dir.replace(/.*\/output\//,'/output/')+'/'+fs[fi];
          links+='<div style="margin:4px 0">📄 '+esc(fs[fi])+' <a href="'+furl+'" target="_blank" class="lnk">打开 ↗</a></div>';
        }
        document.getElementById('outputLinks').innerHTML=links||'无文件';
        // 后续步骤共用 output_dir
        var od=s.output_dir;
        var okCount=0,failCount=0;

        // 3-5: Checker 三步
        var checks=['security','runtime','e2e'];
        var clIds=['cl-security','cl-runtime','cl-e2e'];
        for(var ci=0;ci<checks.length;ci++){
          log.textContent+='['+(3+ci)+'/7] '+checks[ci]+'...\\n';
          try{
            var c=await apiPost('/api/checker/'+checks[ci],{dir:od});
            if(c.json&&c.json.ok){step(clIds[ci],'✅','通过');okCount++;panoMarkRun(checks[ci],true,'');}
            else{
              var _cks=(c.json&&c.json.checks)||[];
              var _fail=_cks.find(function(x){return !x.pass;});
              var detail=_fail?((_fail.name?_fail.name+'：':'')+(_fail.detail||'未通过')):'未通过';
              step(clIds[ci],'❌',detail);failCount++;panoMarkRun(checks[ci],false,detail);
              log.textContent+='  ❌ '+checks[ci]+': '+detail+'\\n';
            }
          }catch(e){step(clIds[ci],'❌',e.message);failCount++;}
        }

        // 6. 推送
        log.textContent+='[6/7] 推送 GitHub...\\n';
        var doPush=document.getElementById('trigReal');
        var pubSubdir='',pubPort='';
        if(doPush&&doPush.checked){
          try{
            var pub=await apiPost('/api/publish',{dir:od,message:'Loop 自动交付 · '+(taskId_sel||'')});
            if(pub.json&&pub.json.ok){
              var pr=pub.json.result||{};
              pubSubdir=pr.subdir||'';pubPort=pr.port||'';
              step('cl-publish','✅','已推送'+(pubSubdir?' → '+pubSubdir:''));
            }
            else{step('cl-publish','⚠️',(pub.json&&(pub.json.error||(pub.json.result&&pub.json.result.reason)))||'未完成');}
          }catch(e){step('cl-publish','❌',e.message);}
        }else{step('cl-publish','⬜','已跳过');}

        // 7. 部署
        log.textContent+='[7/7] 部署 ECS...\\n';
        var doDeploy=document.getElementById('trigECS');
        if(doDeploy&&doDeploy.checked){
          try{
            var dep=await apiPost('/api/deploy',{dir:od,subdir:pubSubdir,port:pubPort});
            if(dep.json&&dep.json.ok){step('cl-deploy','✅',dep.json.url||'已部署');}
            else{step('cl-deploy','⚠️',(dep.json&&(dep.json.error||(dep.json.result&&dep.json.result.reason)))||'未完成');}
          }catch(e){step('cl-deploy','❌',e.message);}
        }else{step('cl-deploy','⬜','已跳过');}

        setRunState('pass','完成');
        break;
      }
    }catch(e){}
    if(poll%5===0)log.textContent+='生成中... ('+(poll*3)+'s)\\n';
  }

  lpRunning=false;btn.disabled=false;
}
function animateAgents(phase){
  var agents=['A1','A2','A3','A4','A5'];
  agents.forEach(function(id){
    var el=document.getElementById('agent-'+id);if(!el)return;
    var st=el.querySelector('.agent-status');
    if(st){st.className='agent-status idle';st.textContent='待命中';}
  });
  if(phase>=1){setAgent('A1','running','分析需求');}
  if(phase>=2){setAgent('A1','done','完成');setAgent('A2','running','生成代码');}
  if(phase>=3){setAgent('A2','done','完成');setAgent('A3','running','审查中');}
  if(phase>=4){setAgent('A3','done','完成');setAgent('A4','running','测试中');}
  if(phase>=5){setAgent('A4','done','完成');setAgent('A5','running','集成中');}
  if(phase>=6){agents.forEach(function(id){setAgent(id,'done','完成');});}
}
function setAgent(id,cls,txt){
  var el=document.getElementById('agent-'+id);if(!el)return;
  var st=el.querySelector('.agent-status');
  if(st){st.className='agent-status '+cls;st.textContent=txt;}
}
async function renderRunsTable(){
  try{var d=await apiGet('/api/trace?limit=10');var events=(d.events||[]).filter(function(e){return e.event==='case_done';});
    var h='';events.reverse().forEach(function(r){h+='<tr><td>'+esc(r._ts||'')+'</td><td>'+esc(r.case||'')+'</td><td>'+(r.result==='pass'?'<span class="badge green">PASS</span>':'<span class="badge red">FAIL</span>')+'</td><td>'+(r.attempts||'?')+'</td><td>'+(r.determinism||'skip')+'</td></tr>';});
    if(!h)h='<tr><td colspan="5" class="hint">暂无</td></tr>';
    document.getElementById('runsBody').innerHTML=h;}
  catch(e){}
}

/* 约束 */
var cfgData={};
async function loadConstraints(manual){
  try{var d=await apiGet('/api/config');cfgData=d.config||{};renderConstraintsForm(cfgData);if(manual)toast('已加载');}
  catch(e){if(manual)toast('未连后端');}
}
function renderConstraintsForm(d){
  var el=document.getElementById('harnessForm');if(!el)return;
  el.innerHTML='<div class="form-row"><label>Harness 版本</label><input value="'+esc(d.harness_version||'')+'" readonly></div>'
    +'<div class="form-row"><label>默认端口</label><input value="'+esc((d.tech||{}).default_port||'')+'" readonly></div>'
    +'<div class="form-row"><label>禁用依赖</label><input value="'+esc((d.banned_deps||[]).join(', '))+'" readonly></div>';
}

/* 设置 */
async function loadSettings(){
  if(!API_LIVE){try{await probeLive(false);}catch(e){}}
  var cfg={};try{var d=await apiGet('/api/config');cfg=d.config||{};}catch(e){}
  var fields=['DEEPSEEK_MODEL','DEEPSEEK_BASE_URL','HARNESS_TEMPERATURE','HARNESS_SEED','HARNESS_MODE','HARNESS_VERIFY_SOURCE','HARNESS_VERIFY_PORT','HARNESS_DET_CHECK','HARNESS_MAX_TASKS','HARNESS_AUTOCOMMIT','HARNESS_GIT_REMOTE','HARNESS_GIT_PUSH','HARNESS_GIT_SUBDIR','ECS_DEPLOY','ECS_HOST','ECS_SSH_USER'];
  fields.forEach(function(k){var el=document.getElementById('cfg_'+k);if(el)el.value=cfg[k]||'';});
  var envEl=document.getElementById('settingsEnv');if(envEl){var lines=[];for(var key in cfg){if(cfg[key])lines.push(key+' = '+cfg[key]);}envEl.textContent=lines.join('\n')||'（未加载到配置）';}
}
function saveSettings(){
  var fields=['DEEPSEEK_MODEL','DEEPSEEK_BASE_URL','HARNESS_TEMPERATURE','HARNESS_SEED','HARNESS_MODE','HARNESS_VERIFY_SOURCE','HARNESS_VERIFY_PORT','HARNESS_DET_CHECK','HARNESS_MAX_TASKS','HARNESS_AUTOCOMMIT','HARNESS_GIT_REMOTE','HARNESS_GIT_PUSH','HARNESS_GIT_SUBDIR','ECS_DEPLOY','ECS_HOST','ECS_SSH_USER'];
  var data={};fields.forEach(function(k){var el=document.getElementById('cfg_'+k);if(el&&el.value!=='')data[k]=el.value;});
  if(!API_LIVE){toast('未连后端，无法保存');return;}
  apiPost('/api/config',data).then(function(r){var st=document.getElementById('settingsStatus');if(r.ok){if(st)st.textContent='已保存';toast('已保存到 config.env');}else{if(st)st.textContent='失败';toast('保存失败');}setTimeout(function(){if(st)st.textContent='';},3000);});
}

/* 需求 CRUD */
async function addBacklog(){
  if(!API_LIVE){toast('未连后端');return;}
  var fsTab=document.getElementById('reqtab-fs');var isText=fsTab&&fsTab.style.display==='none';
  if(isText){
    var title=((document.getElementById('txtTitle')||{}).value||'').trim();
    var desc=((document.getElementById('txtDesc')||{}).value||'').trim();if(!desc){toast('请输入需求描述');return;}
    if(!title)title=desc.slice(0,50);
    var prio=parseInt(((document.getElementById('txtPrio')||{}).value||'2'));
    var body={title:title,spec_text:desc,priority:prio};
    var r=await apiPost('/api/backlog',body);
    if(r.ok&&r.json&&r.json.ok){closeModal('reqModal');toast('已入池 '+r.json.id);loadReqs();loadDashboard();}
    else{toast('入池失败');}
  }else{
    var link=((document.getElementById('fsLink')||{}).value||'').trim();
    var ftitle=((document.getElementById('fsTitle')||{}).value||'').trim();if(!link){toast('请粘贴飞书链接');return;}
    var r=await apiPost('/api/backlog',{link:link,title:ftitle});if(r.ok&&r.json&&r.json.ok){closeModal('reqModal');toast('已入池 '+r.json.id);loadReqs();loadDashboard();}else{toast('入池失败');}
  }
}

/* 初始化 */
// 页面刷新保持状态
try{var lastPage=localStorage.getItem('loop-page');if(lastPage){
  document.querySelectorAll('.nav-item').forEach(function(n){n.classList.remove('active');});
  var nav=document.querySelector('[data-page="'+lastPage+'"]');if(nav)go(nav);}
}catch(e){}
if(!document.querySelector('.page.active')){
  var dash=document.getElementById('page-dashboard');if(dash)dash.classList.add('active');
}
renderGraph('lgConsole',{});
probeLive(false);
