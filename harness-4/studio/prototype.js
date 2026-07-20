/* ============================================================
   Harness-4 需求驱动生成 · 原型交互(全 Mock 数据)
   ============================================================ */

/* ---------- 示例需求 ---------- */
const EXAMPLES = {
  edu:{req:"做一个在线学习平台,首页展示课程卡片(封面、标题、讲师、时长、简介),点进去看课程详情和报名按钮。风格清爽、学习蓝。",name:"education",c1:"#1a73e8",c2:"#34a853"},
  shop:{req:"做一个淘宝风电商,首页是商品列表(图片、标题、价格、销量、店铺),详情页有加入购物车和立即购买。",name:"ecommerce",c1:"#ff5000",c2:"#ff0036"},
  blog:{req:"做一个极简阅读风的博客,首页文章列表(标题、作者、日期、摘要),点进去看正文。墨蓝配色。",name:"blog",c1:"#2c3e50",c2:"#888888"},
  recipe:{req:"做一个美食菜谱站,首页菜谱卡片(封面、菜名、简介),详情页有开始烹饪按钮和步骤。暖橙配色。",name:"recipe",c1:"#e67e22",c2:"#27ae60"},
};

/* ---------- 各用例的规格产物(Step2 mock) ---------- */
const CASE_PRESET = {
  education:{entity:"course",data:"data/courses.json",min:6,marker:"course-card",loader:"load_courses",
    fields:[["id","int","唯一,从 1 递增"],["title","string","课程标题,≤ 50 字"],["teacher","string","讲师名"],["level","string","难度"],["duration","int","时长(分钟),> 0"],["cover","string","封面图路径"],["summary","string","简介,≤ 120 字"],["content","string","正文,≥ 200 字"]],
    children:["course-cover","course-title","course-meta","course-summary"],detail:["btn-enroll","course-outline"],img:true},
  ecommerce:{entity:"product",data:"data/products.json",min:8,marker:"product-card",loader:"load_products",
    fields:[["id","int","唯一,从 1 递增"],["title","string","标题,≤ 40 字"],["price","number","价格,> 0"],["sales","int","销量,≥ 0"],["image","string","主图路径"],["shop","string","店铺名"],["desc","string","描述,≥ 30 字"]],
    children:[],detail:["btn-cart","btn-buy"],img:true},
  blog:{entity:"post",data:"data/posts.json",min:6,marker:"post-card",loader:"load_posts",
    fields:[["id","int","唯一,从 1 递增"],["title","string","标题,≤ 60 字"],["author","string","作者"],["date","string","日期 YYYY-MM-DD"],["summary","string","摘要,≤ 120 字"],["content","string","正文,≥ 200 字"]],
    children:[],detail:["article-body"],img:false},
  recipe:{entity:"recipe",data:"data/recipes.json",min:6,marker:"recipe-card",loader:"load_recipes",
    fields:[["id","int","唯一,从 1 递增"],["title","string","菜名,≤ 50 字"],["cover","string","封面图路径"],["summary","string","简介,≤ 120 字"],["content","string","做法正文,≥ 200 字"]],
    children:["recipe-cover","recipe-title","recipe-summary"],detail:["btn-cook","recipe-steps"],img:true},
};
function buildMock(){
  const name=(document.getElementById('caseName').value.trim())||'education';
  const c1=document.getElementById('color1t').value,c2=document.getElementById('color2t').value;
  return {name,c1,c2,...(CASE_PRESET[name]||CASE_PRESET.education)};
}

/* ============================================================
   Step 3 配置中心:harness-4 全部可配置/可查看文件(Mock)
   ============================================================ */
const CONSTRAINTS = {
  tech:{language:"python",framework:"flask",entry:"app.py",default_port:5000},
  base_required_files:["app.py","requirements.txt","README.md","templates/base.html","templates/list.html","templates/detail.html","static/css/style.css","static/js/main.js","tests/test_app.py"],
  banned_deps:["django","sqlalchemy","flask-sqlalchemy","fastapi","vue","react","jquery","bootstrap","pytest"],
  banned_code_patterns:["eval(","exec(","os.system(","subprocess.","__import__(","pickle.load"],
  max_inline_style:2,
};

/* 框架级文件树。type:constraints|md|env|code;readOnly:派生物只读;lang:代码高亮标签 */
const FILES = {
  "constraints.json":{group:"① 全局硬约束",dir:"harness-4/",type:"constraints"},

  "rules/base/security.md":{group:"② 基座规则 rules/base/",dir:"harness-4/",type:"md",enabled:true,content:"# 安全基线(所有生成任务强制)\n\n- 禁止 `eval`/`exec`/`os.system`/`subprocess`/`__import__`/`pickle.load`\n- 所有外部输入(路由参数、查询串)必须校验类型与范围\n- 详情页 id 转 int,越界/不存在一律 404,不返回异常堆栈\n- 不得读取 data 目录之外的路径"},
  "rules/base/error-and-logging.md":{group:"② 基座规则 rules/base/",dir:"harness-4/",type:"md",enabled:true,content:"# 错误处理与日志\n\n- 数据加载失败要捕获并记日志,不得静默吞掉\n- 404 统一返回 JSON `{\"error\": \"...\"}`\n- 用标准库 logging,禁止裸 print 当日志"},
  "rules/base/testing.md":{group:"② 基座规则 rules/base/",dir:"harness-4/",type:"md",enabled:true,content:"# 测试要求(场景中立,占位符引用 routes)\n\n必测 4 用例:\n1. GET {routes.list} → 200 且含 list_marker\n2. GET {routes.detail_sample} → 200\n3. GET {routes.api_list} → 200 且为数组\n4. GET {routes.api_detail_missing} → 404\n\n用标准库 unittest,禁止 pytest。"},
  "rules/base/documentation.md":{group:"② 基座规则 rules/base/",dir:"harness-4/",type:"md",enabled:true,content:"# 文档与注释\n\n- 必须生成 README.md:运行方式、目录说明、接口列表\n- 路由/loader 函数需 docstring\n- 复杂逻辑补行内注释"},

  "rules/task/tech-stack.md":{group:"③ 任务规则 rules/task/",dir:"harness-4/",type:"md",enabled:true,content:"# 技术栈约束\n\n- Python3 + Flask + Jinja2\n- 数据源:JSON 文件({case.data_file}),只读加载,不引数据库\n- 仅标准库 + Flask,禁用 banned_deps"},
  "rules/task/structure.md":{group:"③ 任务规则 rules/task/",dir:"harness-4/",type:"md",enabled:true,content:"# 目录结构约束\n\n- 入口 app.py;模板 templates/;静态 static/\n- 数据 {case.data_file};图片 static/img/<id>.png\n- 必含 templates/{base,list,detail}.html、static/css/style.css、static/js/main.js、tests/test_app.py"},
  "rules/task/conventions.md":{group:"③ 任务规则 rules/task/",dir:"harness-4/",type:"md",enabled:true,content:"# 编码规范\n\n- 数据加载只允许一个 loader {case.loader_function}\n- 路由函数命名遵循 {case.route_functions}\n- 内联样式 ≤ max_inline_style 处,其余进 style.css"},

  "prompt.md":{group:"④ 系统提示词",dir:"harness-4/",type:"md",enabled:true,content:"# 角色\n你是资深工程师,只能输出一个 JSON 信封:{\"files\":[{\"path\":\"...\",\"content\":\"...\"}]}。\n\n# 通用生成规则(场景中立,无领域词汇)\n- 严格遵守随附 constraints / rules / spec\n- 字段/路由/marker/配色一律以 case.json 为准\n- 不得引入 spec 未声明的字段或依赖\n- 输出必须能直接落盘运行并通过验收"},
  "config.env":{group:"④ 系统提示词",dir:"harness-4/",type:"env",enabled:true,content:"MODEL=deepseek-chat\nTEMPERATURE=0\nSEED=42\nVERIFY_PORT=5000\nHARNESS_CASES=education\nRUN_CASES=education\nDET_CHECK=1\nHARNESS_MODE=real   # real | sample\nMAX_RETRY=3"},

  "tools/run_model.py":{group:"⑤ 生成器 tools/",dir:"harness-4/",type:"code",lang:"python",enabled:true,content:"\"\"\"生成器:real=DeepSeek / sample=离线参考。\n组装 prompt.md + rules/* + spec/* + case.json → 调模型 → 解析 JSON 信封 → 落盘;\nneeds_images 时补占位图;写 meta.json。\"\"\"\ndef generate(case, mode=\"real\"): ...  # 206 行(此处为 Mock 摘要)"},
  "tools/sample_generator.py":{group:"⑤ 生成器 tools/",dir:"harness-4/",type:"code",lang:"python",enabled:true,content:"\"\"\"离线参考生成器:无密钥、确定性,产出必过 verify 的参考实现。\n纯字符串拼接 app/模板/CSS/数据/测试,支持图片与卡片子元素。\"\"\"\ndef build(case): ...  # 307 行(Mock 摘要)"},
  "tools/build_schema.py":{group:"⑤ 生成器 tools/",dir:"harness-4/",type:"code",lang:"python",enabled:true,content:"\"\"\"从事实源 case.json 派生 draft-07 JSON Schema(派生物,不构成第二事实源)。\n遍历 required_fields + field_rules → schemas/<case>.data.schema.json\"\"\""},

  "tools/verify.py":{group:"⑥ 验证器 tools/",dir:"harness-4/",type:"code",lang:"python",enabled:true,content:"\"\"\"深化验证 + run 隔离报告。\n结构/依赖/安全扫描/规范/数据(field_rules)/CSS/unittest/真渲染/UI 子元素;\n起 Flask 轮询就绪,打 404,产出 reports/verify-report.json 与 summary.md。\"\"\""},
  "tools/check_consistency.py":{group:"⑥ 验证器 tools/",dir:"harness-4/",type:"code",lang:"python",enabled:true,content:"\"\"\"自洽性门禁(门禁 1/3,最便宜、无需密钥)。\n校验 case.json 每条事实(字段/数值/marker/颜色/路由)都能在 spec/*.md 找到落点。\"\"\""},

  "setup.sh":{group:"⑦ 编排脚本",dir:"harness-4/",type:"code",lang:"bash",enabled:true,content:"#!/usr/bin/env bash\n# 建 .venv 并安装 Flask\npython3 -m venv .venv && source .venv/bin/activate && pip install flask"},
  "generate.sh":{group:"⑦ 编排脚本",dir:"harness-4/",type:"code",lang:"bash",enabled:true,content:"#!/usr/bin/env bash\n# 多用例闭环:生成 → 验收 → 失败带反馈重试 → 确定性复跑 → 写 runs.jsonl\nfor c in $RUN_CASES; do run_model → verify (retry≤MAX_RETRY) → det-recheck; done"},
  "gate.sh":{group:"⑦ 编排脚本",dir:"harness-4/",type:"code",lang:"bash",enabled:true,content:"#!/usr/bin/env bash\n# 门禁总入口(三关):\ncheck_consistency.py  &&  build_schema.py  &&  bash generate.sh"},

  "ci/github-actions.yml":{group:"⑧ CI",dir:"harness-4/",type:"code",lang:"yaml",enabled:true,content:"name: harness-gate\non: [push, pull_request]\njobs:\n  gate:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: bash harness-4/setup.sh\n      - run: HARNESS_MODE=sample bash harness-4/gate.sh"},

  "schemas/<case>.data.schema.json":{group:"⑨ 派生产物(只读)",dir:"harness-4/",type:"code",lang:"json",readOnly:true,content:"{\n  \"$schema\": \"http://json-schema.org/draft-07/schema#\",\n  \"type\": \"array\",\n  \"items\": { \"type\": \"object\", \"required\": [\"id\",\"title\",...],\n    \"properties\": { \"id\": {\"type\":\"integer\"}, \"title\":{\"type\":\"string\",\"maxLength\":50}, ... } }\n}\n// 由 build_schema.py 从 case.json 自动派生,请勿手改"},

  "checklist.md":{group:"⑩ 验收 & 元信息",dir:"harness-4/",type:"md",enabled:true,content:"# 人工验收 / 新增用例清单\n\n- [ ] case.json 与 spec/*.md 自洽\n- [ ] 列表页含 list_marker,卡片子元素齐全\n- [ ] 详情页含全部 detail_markers\n- [ ] 数据量 ≥ min_items,id 连续\n- [ ] 4 个必测用例全绿\n- [ ] 无 banned_deps / banned_code_patterns\n- [ ] 配色与 ui-spec 一致"},
  "VERSION":{group:"⑩ 验收 & 元信息",dir:"harness-4/",type:"code",lang:"text",readOnly:true,content:"4.0.0"},
  "README.md":{group:"⑩ 验收 & 元信息",dir:"harness-4/",type:"md",enabled:true,content:"# Harness-4:契约驱动的确定性代码生成与验证框架\n\n用确定性脚手架约束非确定性大模型输出,用可执行验证闭环兜底。\n\n## 一分钟上手\n1. bash setup.sh\n2. HARNESS_MODE=sample bash gate.sh(离线自检)\n3. 写 .env 后 bash gate.sh(真实生成)"},
  "baseline/manifest.json":{group:"⑩ 验收 & 元信息",dir:"harness-4/",type:"code",lang:"json",readOnly:true,content:"{\n  \"description\": \"确定性基线:sample 模式产物哈希清单,用于复跑比对\",\n  \"mode\": \"sample\",\n  \"hashes\": { \"education/app.py\": \"sha256:…\", \"education/data/courses.json\": \"sha256:…\" }\n}"},
};

/* 本次用例的动态文件(来自 Step2 的需求拆分) */
function caseFiles(){
  const m=MOCK||buildMock(); const base=`cases/${m.name}/`; const g=`⓪ 本次用例 ${base}`;
  return {
    [base+"case.json"]:{group:g,dir:"harness-4/",type:"code",lang:"json",enabled:true,content:caseJsonText(m)},
    [base+"spec/data-model.md"]:{group:g,dir:"harness-4/",type:"md",readOnly:true,enabled:true,content:specText(m,'data')},
    [base+"spec/api-contract.md"]:{group:g,dir:"harness-4/",type:"md",readOnly:true,enabled:true,content:specText(m,'api')},
    [base+"spec/ui-spec.md"]:{group:g,dir:"harness-4/",type:"md",readOnly:true,enabled:true,content:specText(m,'ui')},
  };
}
function caseJsonText(m){
  return `{
  "name": "${m.name}",
  "entity": "${m.entity}",
  "data_file": "${m.data}",
  "min_items": ${m.min},
  "required_fields": [${m.fields.map(f=>`"${f[0]}"`).join(", ")}],
  "loader_function": "${m.loader}",
  "list_marker": "${m.marker}",
  "list_card_children": [${m.children.map(c=>`"${c}"`).join(", ")}],
  "detail_markers": [${m.detail.map(c=>`"${c}"`).join(", ")}],
  "colors": ["${m.c1}", "${m.c2}"],
  "needs_images": ${m.img},
  "routes": { "list": "/", "api_list": "/api/${m.entity}s" }
}`;
}
function specText(m,kind){
  if(kind==='data'){
    return `# 数据模型:\`${m.data}\`\n\n| 字段 | 类型 | 说明 |\n|---|---|---|\n`+
      m.fields.map(f=>`| ${f[0]} | ${f[1]} | ${f[2]} |`).join("\n")+`\n\n数据量:至少 ${m.min} 项,id 连续。`;
  }
  if(kind==='api'){
    const e=m.entity;
    return `# 接口契约\n\nGET / → 列表页\nGET /${e}/<int:id> → 详情页;不存在返回 404\nGET /api/${e}s → 200,数组\nGET /api/${e}s/<int:id> → 200 / 404 {"error":"${e} not found"}`;
  }
  return `# UI 规范\n\n主色 ${m.c1};强调 ${m.c2}\n列表卡片 class \`${m.marker}\`${m.children.length?';子元素 '+m.children.join(' / '):''}\n详情页元素 ${m.detail.join(' / ')}\n字号:列表 18 / 详情 28 / 正文 16 / 元信息 13 px`;
}

let ALLFILES=null;
let activeFile="constraints.json";
function rebuildFiles(){
  ALLFILES={...caseFiles(),...FILES};
  if(!ALLFILES[activeFile]) activeFile="constraints.json";
}
function iconFor(f){
  if(f.type==="constraints") return "⚙️";
  if(f.type==="env") return "🔧";
  if(f.readOnly) return "🔒";
  if(f.lang==="python") return "📘";
  if(f.lang==="bash") return "📜";
  if(f.lang==="yaml") return "🧾";
  if(f.lang==="json") return "🧩";
  return "📄";
}
function renderTree(){
  const tree=document.getElementById('tree'); const groups={};
  Object.entries(ALLFILES).forEach(([p,f])=>{(groups[f.group]=groups[f.group]||[]).push(p);});
  let html="";
  Object.keys(groups).sort().forEach(g=>{
    html+=`<div class="tree-group">${g}</div>`;
    groups[g].forEach(p=>{
      const f=ALLFILES[p]; const nm=p.split("/").pop();
      let state='';
      if(f.readOnly) state='<span class="dotstate" style="background:#b26a00"></span>';
      else if(f.type!=="constraints") state=`<span class="dotstate ${f.enabled?'':'off'}"></span>`;
      html+=`<div class="tree-file ${p===activeFile?'active':''}" data-p="${p}">
        <span class="fi"><span class="ic">${iconFor(f)}</span><span class="nm">${nm}</span></span>${state}</div>`;
    });
  });
  tree.innerHTML=html;
  tree.querySelectorAll('.tree-file').forEach(el=>el.onclick=()=>{activeFile=el.dataset.p;renderTree();renderEditor();});
}
function renderEditor(){
  const f=ALLFILES[activeFile];
  document.getElementById('epPath').innerHTML=`<span class="dir">${f.dir}</span>${activeFile}`;
  const acts=document.getElementById('epActions'); const body=document.getElementById('epBody');
  let actHtml="";
  if(f.lang) actHtml+=`<span class="code-badge">${f.lang}</span>`;
  if(f.readOnly) actHtml+=`<span class="ro-badge">派生物 · 只读</span>`;
  if(!f.readOnly && f.type!=="constraints"){
    actHtml+=`<span class="locktag">启用</span><label class="switch"><input type="checkbox" id="enSwitch" ${f.enabled?'checked':''}><span class="slider"></span></label>`;
  }
  if(!f.readOnly) actHtml+=`<button class="btn btn-primary btn-sm" onclick="saveFile()">保存(Mock)</button>`;
  acts.innerHTML=actHtml;
  const sw=document.getElementById('enSwitch');
  if(sw) sw.onchange=()=>{f.enabled=sw.checked;renderTree();toast(sw.checked?'已启用':'已停用');};

  if(f.type==="constraints"){ body.innerHTML=constraintsForm(); bindConstraints(); return; }
  const note=f.readOnly?`<div class="ro-note">⚠ 此文件由 Harness 自动派生/维护,不建议手改(改事实源后会被覆盖)。</div>`:
    `<div class="hint">${f.type==="env"?'运行参数,控制模型/确定性/模式':(f.lang?'框架代码 / 脚本(高级)':'规则文本,拼进系统提示词喂给模型')}。</div>`;
  body.innerHTML=note+`<textarea class="code-edit" id="codeEdit" ${f.readOnly?'readonly':''}>${escapeHtml(f.content)}</textarea>`;
  if(!f.readOnly) document.getElementById('codeEdit').oninput=e=>{f.content=e.target.value;};
}
function constraintsForm(){
  const c=CONSTRAINTS;
  return `<div class="hint">全局硬约束,对所有用例统一生效。技术栈锁定产物形态;禁用项是安全护栏。</div>
  <div class="subhead">技术栈 tech <span class="locktag">影响产物形态</span></div>
  <div class="fgrid">
    <div class="fitem"><label>language</label><input id="c-lang" value="${c.tech.language}"></div>
    <div class="fitem"><label>framework</label><input id="c-fw" value="${c.tech.framework}"></div>
    <div class="fitem"><label>entry</label><input id="c-entry" value="${c.tech.entry}"></div>
    <div class="fitem"><label>default_port</label><input id="c-port" value="${c.tech.default_port}"></div>
  </div>
  <div class="subhead">禁用依赖 banned_deps</div><div class="taglist" id="tl-deps"></div>
  <div class="subhead">禁用代码模式 banned_code_patterns</div><div class="taglist" id="tl-pat"></div>
  <div class="subhead">max_inline_style</div><div class="fitem" style="max-width:160px"><input id="c-mis" value="${c.max_inline_style}"></div>
  <div class="subhead">必备文件 base_required_files <span class="locktag">${c.base_required_files.length} 个</span></div>
  <div class="filelist">${c.base_required_files.map(x=>`<div class="fl"><span>${x}</span><span style="color:var(--muted)">必备</span></div>`).join('')}</div>`;
}
function renderTags(id,arr){
  const box=document.getElementById(id);
  const render=()=>{
    box.innerHTML=arr.map((t,i)=>`<span class="t">${escapeHtml(t)}<span class="x" data-i="${i}">✕</span></span>`).join('')+`<input placeholder="+ 添加,回车确认">`;
    box.querySelectorAll('.x').forEach(x=>x.onclick=()=>{arr.splice(+x.dataset.i,1);render();});
    const inp=box.querySelector('input'); inp.onkeydown=e=>{if(e.key==='Enter'&&inp.value.trim()){arr.push(inp.value.trim());render();}};
  };
  render();
}
function bindConstraints(){
  renderTags('tl-deps',CONSTRAINTS.banned_deps); renderTags('tl-pat',CONSTRAINTS.banned_code_patterns);
  const map={'c-lang':['tech','language'],'c-fw':['tech','framework'],'c-entry':['tech','entry'],'c-port':['tech','default_port']};
  Object.entries(map).forEach(([id,[a,b]])=>{const el=document.getElementById(id);if(el)el.oninput=()=>CONSTRAINTS[a][b]=el.value;});
  const mis=document.getElementById('c-mis'); if(mis) mis.oninput=()=>CONSTRAINTS.max_inline_style=mis.value;
}
function saveFile(){toast(`已保存(Mock):${activeFile} → 内存,后续对接真实写盘`);}

/* ============================================================
   步骤切换
   ============================================================ */
let cur=1;
function goto(n){
  cur=n;
  [1,2,3,4].forEach(i=>document.getElementById('p'+i).classList.toggle('hidden',i!==n));
  document.querySelectorAll('#stepper .step').forEach(el=>{const s=+el.dataset.s;el.classList.toggle('active',s===n);el.classList.toggle('done',s<n);});
  window.scrollTo({top:0,behavior:'smooth'});
}
document.querySelectorAll('#stepper .step').forEach(el=>el.onclick=()=>goto(+el.dataset.s));
document.getElementById('examples').addEventListener('click',e=>{
  const ex=e.target.dataset.ex; if(!ex) return; const d=EXAMPLES[ex];
  document.getElementById('req').value=d.req; document.getElementById('caseName').value=d.name;
  ['color1','color1t'].forEach(id=>document.getElementById(id).value=d.c1);
  ['color2','color2t'].forEach(id=>document.getElementById(id).value=d.c2);
});
const bindColor=(a,b)=>{const A=document.getElementById(a),B=document.getElementById(b);A.oninput=()=>B.value=A.value;B.oninput=()=>A.value=B.value;};
bindColor('color1','color1t'); bindColor('color2','color2t');

/* ============================================================
   Step2 拆分规格
   ============================================================ */
let MOCK=null;
function toStep2(){
  goto(2);
  document.getElementById('p2-thinking').classList.remove('hidden');
  document.getElementById('p2-body').classList.add('hidden');
  document.getElementById('p2next').disabled=true;
  setTimeout(()=>{
    MOCK=buildMock(); renderFact(MOCK); renderSpec('data');
    document.getElementById('p2-thinking').classList.add('hidden');
    const body=document.getElementById('p2-body'); body.classList.remove('hidden'); body.classList.add('fade');
    document.getElementById('p2next').disabled=false;
  },1300);
}
function renderFact(m){
  const q=s=>`<span class="s">"${s}"</span>`,k=s=>`<span class="k">"${s}"</span>`;
  document.getElementById('factJson').innerHTML=
`{
  ${k('name')}: ${q(m.name)},
  ${k('entity')}: ${q(m.entity)},
  ${k('data_file')}: ${q(m.data)},
  ${k('min_items')}: <span class="n">${m.min}</span>,
  ${k('required_fields')}: [${m.fields.map(f=>q(f[0])).join(', ')}],
  ${k('list_marker')}: ${q(m.marker)},
  ${k('detail_markers')}: [${m.detail.map(q).join(', ')}],
  ${k('colors')}: [${q(m.c1)}, ${q(m.c2)}],
  ${k('routes')}: { ${k('list')}: ${q('/')}, ${k('api_list')}: ${q('/api/'+m.entity+'s')} }
}`;
}
function renderSpec(kind){
  const m=MOCK; let h='';
  if(kind==='data'){
    h=`<h3>数据模型 · <code>${m.data}</code></h3><table><tr><th>字段</th><th>类型</th><th>说明</th></tr>`+
      m.fields.map(f=>`<tr><td><code>${f[0]}</code></td><td>${f[1]}</td><td>${f[2]}</td></tr>`).join('')+
      `</table><p>数据量:至少 <b>${m.min}</b> 项,id 连续。</p>`;
  }else if(kind==='api'){
    const e=m.entity;
    h=`<h3>接口契约</h3>
      <p><code>GET /</code> → 列表页,渲染全部 ${e} 卡片</p>
      <p><code>GET /${e}/&lt;int:id&gt;</code> → 详情页;不存在返回 <b>404</b></p>
      <p><code>GET /api/${e}s</code> → 200,${e} 数组</p>
      <p><code>GET /api/${e}s/&lt;int:id&gt;</code> → 200 单个 / 404 <code>{"error":"${e} not found"}</code></p>`;
  }else{
    h=`<h3>UI 规范</h3>
      <p>主色 <span class="tag" style="background:${m.c1}22;color:${m.c1}">${m.c1}</span> 强调 <span class="tag" style="background:${m.c2}22;color:${m.c2}">${m.c2}</span></p>
      <p>列表卡片根元素 <code>${m.marker}</code>${m.children.length?',含子元素:'+m.children.map(c=>`<code>${c}</code>`).join(' '):''}</p>
      <p>详情页关键元素:${m.detail.map(c=>`<code>${c}</code>`).join(' ')}</p>
      <p>字号:列表标题 18px · 详情标题 28px · 正文 16px · 元信息 13px</p>`;
  }
  document.getElementById('specDoc').innerHTML=h;
}
document.querySelector('.spec-tabs').addEventListener('click',e=>{
  const d=e.target.dataset.d; if(!d) return;
  document.querySelectorAll('.spec-tab').forEach(t=>t.classList.toggle('active',t===e.target)); renderSpec(d);
});
function toStep3(){goto(3);rebuildFiles();renderTree();renderEditor();}
function toStep4(){goto(4);renderComps();}

/* ============================================================
   Step4 运行:组件调用 + 详细日志 + 输出目录
   ============================================================ */
let mode='gate';
document.getElementById('modes').addEventListener('click',e=>{
  const el=e.target.closest('.mode'); if(!el) return;
  mode=el.dataset.m; document.querySelectorAll('.mode').forEach(x=>x.classList.toggle('sel',x===el)); renderComps();
});

/* 每种模式按执行顺序调用的组件 */
const COMPS={
  once:[["config.env","载入参数"],["tools/run_model.py","调模型生成"],["tools/verify.py","验收"]],
  gate:[["config.env","载入参数"],["check_consistency.py","自洽门禁"],["build_schema.py","派生 Schema"],["run_model.py","调模型生成"],["verify.py","全维度验收"],["runs.jsonl","确定性记录"]],
  loop:[["config.env","载入参数"],["check_consistency.py","自洽门禁"],["run_model.py","生成(轮1)"],["verify.py","验收(失败)"],["run_model.py","重试(轮2)"],["verify.py","验收(通过)"],["runs.jsonl","收敛记录"]],
};
function renderComps(){
  const row=document.getElementById('compRow');
  row.innerHTML=COMPS[mode].map((c,k)=>`<div class="comp" data-k="${k}"><span class="cdot"></span><span class="cn">${c[0]}</span><span class="cr">· ${c[1]}</span></div>`).join('');
}
function updateComps(frac){
  const chips=document.querySelectorAll('#compRow .comp'); const K=chips.length;
  chips.forEach((el,k)=>{
    el.classList.remove('run','ok2');
    if(frac>=(k+1)/K) el.classList.add('ok2');
    else if(frac>=k/K) el.classList.add('run');
  });
}

const SCRIPTS={
  once:[["dim","$ bash harness-4/generate.sh --once   # 载入 config.env: MODEL=deepseek-chat TEMPERATURE=0 SEED=42"],
    ["b","▷ tools/run_model.py  组装 prompt.md + rules/* + spec/* + case.json → 调模型"],
    ["dim","    ← 解析 JSON 信封,写入 9 个文件到 output/{ts}-{n}/"],
    ["b","▷ tools/verify.py  起 Flask 验收…"],
    ["ok","    ✓ 结构/数据/渲染/单测 全过"],
    ["ok","✔ 完成 · 产物 output/{ts}-{n}/"]],
  gate:[["dim","$ bash harness-4/gate.sh   # 载入 config.env(MODEL/TEMPERATURE=0/SEED=42/HARNESS_MODE=real)"],
    ["b","── 关卡 1/3 · 自洽性 ── tools/check_consistency.py"],
    ["dim","    读取 constraints.json + cases/{n}/case.json + spec/*.md"],
    ["ok","    ✓ min_items / 字段 / 路由 / marker / 配色 均在 spec 有落点"],
    ["b","── 关卡 2/3 · 派生 Schema ── tools/build_schema.py"],
    ["dim","    遍历 required_fields + field_rules → draft-07"],
    ["ok","    ✓ 写出 schemas/{n}.data.schema.json"],
    ["b","── 关卡 3/3 · 生成+验收 ── generate.sh"],
    ["dim","    组装提示词:prompt.md + rules/base/*(4) + rules/task/*(3) + spec/*(3) + case.json"],
    ["b","    ▷ tools/run_model.py 调模型(deepseek-chat, T=0, seed=42)…"],
    ["dim","      ← 解析 JSON 信封,落盘 9 个必备文件"],
    ["dim","      ← needs_images=true:生成 static/img/1..{min}.png 占位图"],
    ["b","    ▷ tools/verify.py 验收(起 Flask,轮询 / 就绪)…"],
    ["ok","      ✓ 结构:9 必备文件齐全"],
    ["ok","      ✓ 依赖:无 banned_deps;安全:无 banned_code_patterns"],
    ["ok","      ✓ 数据:{min} 条,id 连续,field_rules(max_len/min_len/gt) 全过"],
    ["ok","      ✓ 渲染:list 含 {marker} 及子元素;detail 含 {detail}"],
    ["ok","      ✓ 接口:/api/{n}s 200 数组;/api/{n}s/9999 → 404"],
    ["ok","      ✓ 单测:unittest 4/4 通过"],
    ["b","    ▷ 确定性复跑 + 产物哈希比对 → output/runs.jsonl"],
    ["ok","      ✓ identical(seed 复现一致)"],
    ["ok","✔ 门禁全绿 · 报告:output/{ts}-{n}/reports/verify-report.json + summary.md"]],
  loop:[["dim","$ bash harness-4/gate.sh --loop   # MAX_RETRY=3"],
    ["ok","关卡1 自洽 ✓   关卡2 派生 Schema ✓"],
    ["b","▶ 轮 1 · tools/run_model.py 生成 → tools/verify.py 验收"],
    ["err","    ✗ UI 校验失败:卡片缺少子元素 {child}"],
    ["warn","    ↻ 把 verify-report.json 关键失败点回喂模型,重试…"],
    ["b","▶ 轮 2 · tools/run_model.py 重新生成 → tools/verify.py 验收"],
    ["ok","    ✓ 结构 ✓ 字段规则 ✓ 渲染 ✓ 单测 ✓ 安全"],
    ["b","    ▷ 确定性复跑 → output/runs.jsonl(记录收敛轮次)"],
    ["ok","✔ Loop 收敛通过(2/3 轮)· output/{ts}-{n}/"]],
};

function fmt(txt,m){
  return txt.replace(/{n}/g,m.name).replace(/{min}/g,m.min).replace(/{marker}/g,m.marker)
    .replace(/{detail}/g,m.detail.join('/')).replace(/{child}/g,(m.children[m.children.length-1]||'子元素'))
    .replace(/{ts}/g,'20260720-101530');
}
function runPipeline(){
  const m=MOCK||buildMock();
  const script=SCRIPTS[mode].map(l=>[l[0],fmt(l[1],m)]);
  const con=document.getElementById('console');con.innerHTML='';
  const prog=document.getElementById('prog'),ptext=document.getElementById('progtext'),banner=document.getElementById('banner');
  banner.classList.remove('show'); document.getElementById('outputPanel').classList.add('hidden');
  document.getElementById('runBtn').disabled=true; renderComps(); updateComps(0);
  let i=0;const total=script.length;
  const tick=()=>{
    if(i>=total){
      prog.style.width='100%';ptext.textContent='完成'; updateComps(1);
      banner.className='result-banner show';
      banner.innerHTML=mode==='loop'?'🎉 Loop 自动收敛通过 · 无人值守完成生成与验收 · 报告可逐项追溯。':'🎉 验收通过 · 确定性脚手架约束下生成完成 · 产物与报告已落盘。';
      showOutput(m); document.getElementById('runBtn').disabled=false; return;
    }
    const [cls,txt]=script[i];
    const line=document.createElement('div');line.className=cls;line.textContent=txt;con.appendChild(line);con.scrollTop=con.scrollHeight;
    i++; const frac=i/total; prog.style.width=Math.round(frac*100)+'%';ptext.textContent=Math.round(frac*100)+'%'; updateComps(frac);
    setTimeout(tick,cls==='dim'?420:680);
  };
  tick();
}

/* ---------- 输出目录树 + 文件查看 ---------- */
function buildOutput(m){
  const ts='20260720-101530', root=`output/${ts}-${m.name}/`;
  // 每行:{label, depth, dir?, note?, key?}
  const tree=[
    {label:'app.py',depth:0,key:'app.py'},
    {label:'requirements.txt',depth:0},
    {label:'README.md',depth:0,key:'README.md'},
    {label:'templates/',depth:0,dir:true},
    {label:'base.html',depth:1},{label:'list.html',depth:1,key:'list.html'},{label:'detail.html',depth:1},
    {label:'static/',depth:0,dir:true},
    {label:'css/style.css',depth:1,key:'style.css'},{label:'js/main.js',depth:1},
    ...(m.img?[{label:`img/  (1.png … ${m.min}.png · 占位图)`,depth:1,note:true}]:[]),
    {label:m.data.replace('data/',''),depth:0,dir:false,key:m.data,pathLabel:m.data},
    {label:'tests/test_app.py',depth:0},
    {label:'meta.json',depth:0,key:'meta.json'},
    {label:'reports/',depth:0,dir:true},
    {label:'verify-report.json',depth:1,key:'reports/verify-report.json'},
    {label:'summary.md',depth:1,key:'reports/summary.md'},
  ];
  const contents={
    'app.py':`from flask import Flask, jsonify, render_template, abort\nimport json, logging\napp = Flask(__name__)\n\ndef ${m.loader}():\n    """唯一数据加载器"""\n    with open("${m.data}", encoding="utf-8") as f:\n        return json.load(f)\n\n@app.route("/")\ndef ${m.entity}_list():\n    return render_template("list.html", items=${m.loader}())\n\n@app.route("/${m.entity}/<int:id>")\ndef ${m.entity}_detail(id):\n    item = next((x for x in ${m.loader}() if x["id"]==id), None)\n    if not item: abort(404)\n    return render_template("detail.html", item=item)\n\n@app.route("/api/${m.entity}s/<int:id>")\ndef api_${m.entity}_detail(id):\n    item = next((x for x in ${m.loader}() if x["id"]==id), None)\n    if not item: return jsonify({"error":"${m.entity} not found"}), 404\n    return jsonify(item)`,
    'README.md':`# ${m.name} 应用(Harness 生成)\n\n## 运行\n\`python app.py\` → http://localhost:5000\n\n## 接口\n- GET / 列表页\n- GET /${m.entity}/<id> 详情页\n- GET /api/${m.entity}s 列表 JSON\n- GET /api/${m.entity}s/<id> 详情 JSON(404 兜底)`,
    'list.html':`{% extends "base.html" %}\n{% block body %}\n<div class="grid">\n  {% for x in items %}\n  <a class="${m.marker}" href="/${m.entity}/{{ x.id }}">\n    ${m.children.map(c=>`<div class="${c}">…</div>`).join('\\n    ')||'<h3>{{ x.title }}</h3>'}\n  </a>\n  {% endfor %}\n</div>\n{% endblock %}`,
    'style.css':`:root{ --primary:${m.c1}; --accent:${m.c2}; }\n.${m.marker}{ border:1px solid #eee; border-radius:10px; }\n.${m.marker}:hover h3{ color:${m.c1}; }\n/* 列表标题18 详情28 正文16 元信息13 */`,
    [m.data]:`[\n  { ${m.fields.map(f=>`"${f[0]}": ${sample(f,1)}`).join(", ")} },\n  { ${m.fields.map(f=>`"${f[0]}": ${sample(f,2)}`).join(", ")} }\n  … 共 ${m.min} 条\n]`,
    'meta.json':`{\n  "case": "${m.name}",\n  "model": "deepseek-chat",\n  "temperature": 0,\n  "seed": 42,\n  "mode": "real",\n  "files_written": 9,\n  "duration_ms": 18423,\n  "determinism": "identical",\n  "output_hash": "sha256:${Math.random().toString(16).slice(2,14)}…"\n}`,
    'reports/verify-report.json':`{\n  "case": "${m.name}",\n  "passed": true,\n  "checks": {\n    "structure": {"ok": true, "required_files": 9},\n    "dependencies": {"ok": true, "banned_found": []},\n    "security": {"ok": true, "banned_patterns_found": []},\n    "data": {"ok": true, "count": ${m.min}, "id_sequential": true, "field_rules": "pass"},\n    "render_list": {"ok": true, "marker": "${m.marker}", "card_children": ${JSON.stringify(m.children)}},\n    "render_detail": {"ok": true, "markers": ${JSON.stringify(m.detail)}},\n    "api": {"list_200": true, "detail_404": true},\n    "unittest": {"ok": true, "run": 4, "passed": 4}\n  },\n  "reruns": [{"hash":"sha256:…","result":"identical"}]\n}`,
    'reports/summary.md':`# 验收报告 · ${m.name}\n\n**结论:✅ PASS**(8/8 检查项)\n\n| 维度 | 结果 |\n|---|---|\n| 结构 | ✓ 9 必备文件 |\n| 依赖 | ✓ 无 banned_deps |\n| 安全 | ✓ 无危险调用 |\n| 数据 | ✓ ${m.min} 条 · id 连续 · field_rules 全过 |\n| 列表渲染 | ✓ ${m.marker}${m.children.length?' + '+m.children.length+' 子元素':''} |\n| 详情渲染 | ✓ ${m.detail.join(' / ')} |\n| 接口 | ✓ 200 数组 / 404 |\n| 单测 | ✓ 4/4 |\n\n确定性复跑:identical(seed=42)`,
  };
  return {root,tree,contents};
}
function sample(f,i){
  if(f[0]==='id') return i;
  if(f[1]==='int') return 60*i; if(f[1]==='number') return (9.9*i).toFixed(1);
  if(f[0]==='cover'||f[0]==='image') return `"static/img/${i}.png"`;
  return `"示例${f[0]}${i}"`;
}
let OUT=null;
function showOutput(m){
  OUT=buildOutput(m);
  document.getElementById('outPath').textContent=OUT.root;
  const tree=document.getElementById('otree');
  let html=`<span class="dn">${OUT.root}</span>\n`;
  OUT.tree.forEach((r,idx)=>{
    const last=idx===OUT.tree.length-1;
    const indent=r.depth>0?'│   ':'';
    const conn=last?'└── ':'├── ';
    if(r.dir){ html+=`${indent}${conn}<span class="dn">${r.label}</span>\n`; }
    else if(r.note){ html+=`${indent}${conn}<span class="dn">${r.label}</span>\n`; }
    else if(r.key){ html+=`${indent}${conn}<span class="f" data-k="${r.key}">${r.label}</span>\n`; }
    else { html+=`${indent}${conn}<span class="f" data-k="">${r.label}</span>\n`; }
  });
  tree.innerHTML=html;
  tree.querySelectorAll('.f').forEach(el=>el.onclick=()=>{
    tree.querySelectorAll('.f').forEach(x=>x.classList.remove('sel')); el.classList.add('sel');
    const k=el.dataset.k; const v=k?OUT.contents[k]:null;
    document.getElementById('oviewer').innerHTML= v
      ? `<div class="ovh"># ${OUT.root}${k}</div><pre>${escapeHtml(v)}</pre>`
      : `<div class="ovh"># ${OUT.root}${el.textContent.trim()}</div><pre>(该文件未提供 Mock 预览)</pre>`;
  });
  document.getElementById('oviewer').innerHTML=`<div class="ovh"># 点击左侧文件查看内容(Mock)· 已生成 ${OUT.tree.filter(r=>!r.dir&&!r.note).length} 个文件</div>`;
  document.getElementById('outputPanel').classList.remove('hidden');
}

/* ---------- 工具 ---------- */
function escapeHtml(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
let toastTimer=null;
function toast(msg){
  const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),2200);
}
