import {rectangle,extent,traverse,hitTest} from "./core.mjs";

const $=id=>document.getElementById(id), NS="http://www.w3.org/2000/svg";
let nodes=new Map(),rows=new Map(),shapes=new Map(),controller=null,epoch=0;
let selected=null,world=null,scale=.4,calls=0,logs=[],sessionToken=null,diff={nodes:{},deleted:[],root:null};
const make=(tag,attrs={})=>{const e=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));return e;};
function status(message,state="loading"){$("status").textContent=message;$("status").dataset.state=state;$("status").classList.toggle("error",state==="error");}
async function request(url,body,signal){
  const r=await fetch(url,{method:body?"POST":"GET",headers:body?{"Content-Type":"application/json"}:{},body:body?JSON.stringify(body):undefined,signal});
  const data=await r.json();if(!r.ok)throw new Error(data.error||`HTTP ${r.status}`);return data;
}
const publicAttributes=value=>Object.fromEntries(Object.entries(value).filter(([,v])=>v!==""));
function attributes(node){return publicAttributes({...node.details,children:node.children,text:node.ownText,content:node.entries});}
function showProperties(target,value,change){
  target.replaceChildren();
  const keys=new Set([...Object.keys(value),...Object.keys(change?.attributes||{})]);
  for(const key of keys){
    const line=document.createElement("div"),field=change?.attributes?.[key];
    if(field){line.className="changed-attribute";line.textContent=`${key}: ${JSON.stringify(field.before)} → ${JSON.stringify(field.after)}`;}
    else line.textContent=`${key}: ${JSON.stringify(value[key])}`;
    target.append(line);
  }
}
function renderChanges(){
  const panel=$("changes");panel.replaceChildren();
  panel.hidden=!Object.keys(diff.nodes).length && !diff.deleted.length;
  const title=document.createElement("div");title.textContent=`Sync：${Object.keys(diff.nodes).length} 个变化节点 · ${diff.deleted.length} 个删除节点 · 变化根 ${diff.root??"无"}`;panel.append(title);
  for(const node of diff.deleted){
    const button=document.createElement("button");button.className="deleted-node";button.textContent=`已删除 #${node.id} ${node.summary||node.type}`;
    button.addEventListener("click",()=>{$("selected-title").textContent=`已删除区域 #${node.id}`;showProperties($("properties"),node,{attributes:Object.fromEntries(Object.entries(node).map(([k,v])=>[k,{before:v,after:null}]))});});panel.append(button);
  }
}
function hit(event){
  const point=new DOMPoint(event.clientX,event.clientY).matrixTransform($("canvas").getScreenCTM().inverse());
  return hitTest(nodes,point.x,point.y);
}
function hover(id,event){
  for(const el of document.querySelectorAll(".hover"))el.classList.remove("hover");
  if(id==null){$("tooltip").hidden=true;return;}
  rows.get(id)?.classList.add("hover");shapes.get(id)?.classList.add("hover");
  const n=nodes.get(id);showProperties($("tooltip"),publicAttributes({...n.details,text:n.ownText}),diff.nodes[id]);
  $("tooltip").hidden=false;
  $("tooltip").style.left=`${Math.max(8,Math.min(event.clientX+15,innerWidth-390))}px`;
  $("tooltip").style.top=`${Math.max(8,Math.min(event.clientY+15,innerHeight-325))}px`;
}
function select(id,from){
  selected=id;document.body.dataset.selected=String(id);
  for(const el of document.querySelectorAll(".selected"))el.classList.remove("selected");
  rows.get(id)?.classList.add("selected");shapes.get(id)?.classList.add("selected");
  const node=nodes.get(id),row=rows.get(id);
  // Reveal ancestors only. Opening the selected details here would run before
  // summary's native toggle and immediately close a previously collapsed node.
  let ancestor=row?.parentElement?.parentElement;
  while(ancestor && ancestor!==$("tree")){if(ancestor.tagName==="DETAILS")ancestor.open=true;ancestor=ancestor.parentElement;}
  if(from==="canvas")row?.scrollIntoView({block:"nearest",behavior:"smooth"});
  const b=rectangle(node.bounds);
  document.getElementById("selection-outline")?.remove();
  if(b){
    $("canvas").append(make("rect",{id:"selection-outline",class:"selection-outline",x:b.x,y:b.y,width:b.width,height:b.height}));
    if(from==="tree"){
      const viewport=$("viewport");
      viewport.scrollTo({left:Math.max(0,(b.x-world.x)*scale-40),top:Math.max(0,(b.y-world.y)*scale-70),behavior:"smooth"});
    }
  }
  $("selected-title").textContent=`区域 #${id} · 公开属性与完整区域文本`;
  showProperties($("properties"),attributes(node),diff.nodes[id]);
}
function paintText(group,node,b){
  if(!node.ownText || b.invalid)return;
  const font=Math.max(11,Math.min(25,b.height*.55));
  const lineHeight=font*1.2,maxLines=Math.min(4,Math.floor(b.height/lineHeight));
  const length=Math.max(1,Math.floor((b.width-8)/font));
  if(!maxLines)return;
  const chars=Array.from(node.ownText),text=make("text",{"font-size":font,"clip-path":`url(#clip-${node.id})`});
  for(let i=0;i<maxLines && i*length<chars.length;i++){
    const span=make("tspan",{x:b.x+3,y:b.y+font+i*lineHeight});
    span.textContent=chars.slice(i*length,(i+1)*length).join("")+(i===maxLines-1 && chars.length>(i+1)*length?"…":"");text.append(span);
  }
  group.append(text);
}
function renderCanvas(){
  shapes=new Map();const svg=$("canvas");svg.replaceChildren();world=extent(new Map([...nodes,...diff.deleted.map(n=>["deleted-"+n.id,n])]));
  svg.setAttribute("viewBox",`${world.x} ${world.y} ${world.width} ${world.height}`);
  const defs=make("defs");svg.append(defs);
  svg.append(make("line",{class:"axis",x1:0,y1:world.y,x2:0,y2:world.y+world.height}));
  svg.append(make("line",{class:"axis",x1:world.x,y1:0,x2:world.x+world.width,y2:0}));
  const zero=make("text",{x:6,y:-10,"font-size":14,fill:"#6b7d95"});zero.textContent="(0, 0)  x →  y ↓";svg.append(zero);
  for(const node of diff.deleted){
    const b=rectangle(node.bounds);if(b)svg.append(make("rect",{class:"deleted-region",x:b.x,y:b.y,width:b.width,height:b.height}));
  }
  let invalid=0,missing=0;
  for(const node of nodes.values()){
    const b=rectangle(node.bounds);if(!b){missing++;continue;}if(b.invalid)invalid++;
    const g=make("g",{class:`region${b.invalid?" invalid":""}${diff.nodes[node.id]?" changed":""}`,"data-id":node.id,tabindex:0,role:"button","aria-label":`区域 ${node.id}: ${node.summary??""}`});
    const clip=make("clipPath",{id:`clip-${node.id}`});clip.append(make("rect",{x:b.x,y:b.y,width:b.width,height:b.height}));defs.append(clip);
    const color=`hsl(${(node.depth*43+205)%360} 55% 52%)`;
    g.append(make("rect",{x:b.x,y:b.y,width:b.width,height:b.height,stroke:color,fill:color}));
    if($("labels").checked)paintText(g,node,b);
    g.addEventListener("click",e=>{e.stopPropagation();const id=hit(e);if(id!=null)select(id,"canvas");});
    g.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();select(node.id,"canvas");}});
    g.addEventListener("pointermove",e=>hover(hit(e),e));g.addEventListener("pointerleave",()=>hover(null));
    svg.append(g);shapes.set(node.id,g);
  }
  $("extent").textContent=`x [${world.x+40}, ${world.x+world.width-40}] · y [${world.y+40}, ${world.y+world.height-40}]`;
  svg.dataset.invalid=invalid;svg.dataset.missing=missing;
  applyScale();if(selected!=null)select(selected,"render");
}
function renderTree(){
  rows=new Map();$("tree").replaceChildren();
  function branch(id){
    const n=nodes.get(id),container=document.createElement(n.children.length?"details":"div");
    container.className=`branch${n.parent==null?" root":""}`;container.dataset.id=id;
    if(n.children.length)container.open=n.depth<2;
    const row=document.createElement(n.children.length?"summary":"div");row.className="node-row"+(diff.nodes[id]?" changed":"");row.dataset.id=id;
    if(!n.children.length){row.tabIndex=0;row.setAttribute("role","button");}
    const tag=document.createElement("span");tag.className="tag";tag.textContent="<region ";
    const attr=document.createElement("span");attr.className="attribute";attr.textContent=`id="${id}" `;
    const label=document.createElement("span");label.textContent=`${n.summary ? "summary="+JSON.stringify(n.summary) : ""}${n.children.length?">":" />"}`;
    if(diff.nodes[id]?.attributes?.summary)label.classList.add("changed-attribute");
    row.append(tag,attr,label);container.append(row);rows.set(id,row);
    row.addEventListener("click",()=>select(id,"tree"));
    if(!n.children.length)row.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();select(id,"tree");}});
    row.addEventListener("pointermove",e=>hover(id,e));row.addEventListener("pointerleave",()=>hover(null));
    if(n.ownText){const text=document.createElement("div");text.className="node-text";text.textContent=n.ownText;container.append(text);}
    for(const child of n.children)container.append(branch(child));
    if(n.children.length){const end=document.createElement("div");end.className="closing";end.textContent="</region>";container.append(end);}
    return container;
  }
  $("tree").append(branch([...nodes.keys()][0]));
}
function applyScale(){if(!world)return;$("canvas").style.width=`${world.width*scale}px`;$("canvas").style.height=`${world.height*scale}px`;$("scale").textContent=`${Math.round(scale*100)}%`;$("zoom").value=Math.round(scale*100);}
function fit(){if(!world)return;scale=Math.max(.1,Math.min(2,($("viewport").clientWidth-26)/world.width));applyScale();}
async function load(){
  const version=++epoch;controller?.abort();controller=new AbortController();const {signal}=controller;
  const active=()=>{if(version!==epoch)throw new DOMException("Superseded","AbortError");};
  diff={nodes:{},deleted:[],root:null};renderChanges();nodes=new Map();selected=null;world=null;calls=0;logs=[];document.body.dataset.selected="";
  $("canvas").replaceChildren();$("tree").replaceChildren();$("properties").textContent="正在从根读取…";
  $("empty").hidden=false;$("empty").textContent="正在遍历公开区域接口…";$("stop").disabled=false;
  $("trace").textContent="";$("call-count").textContent="0";hover(null);status("正在创建读取会话…");
  try{
    const syncing=$("sync").checked && sessionToken;
    const response=await request(syncing?"/api/sync":"/api/session",{case:$("cases").value,...(syncing?{session:sessionToken}:{})},signal);active();
    async function call(name,args){
      active();const began=performance.now();const result=await request("/api/tool",{session:response.session,name,arguments:args},signal);active();
      calls++;logs.push(`${String(calls).padStart(3)}  ${name} ${JSON.stringify(args)}  ${Math.round(performance.now()-began)}ms`);
      $("call-count").textContent=calls;
      return result;
    }
    const result=await traverse(call,response.initial.page,map=>status(`读取 ${map.size} 个区域 · ${calls} 次工具调用`));active();
    sessionToken=response.session;diff=response.diff;nodes=result;renderChanges();renderTree();renderCanvas();fit();$("empty").hidden=true;
    $("properties").textContent="悬停查看属性，点击固定详情。";
    $("trace").textContent=logs.join("\n");document.body.dataset.nodes=nodes.size;
    const missing=Number($("canvas").dataset.missing),invalid=Number($("canvas").dataset.invalid);
    status(`${nodes.size} 个区域 · ${calls} 次调用${invalid?` · ${invalid} 个异常框`:""}${missing?` · ${missing} 个无坐标区域`:""}`,"ready");
  }catch(error){
    if(version!==epoch)return;
    const stopped=error.name==="AbortError";status(stopped?"读取已停止":error.message,stopped?"stopped":"error");
    $("empty").textContent=stopped?"读取已停止，可重新读取":"读取失败："+error.message;
    $("trace").textContent=logs.join("\n");
  }finally{if(version===epoch)$("stop").disabled=true;}
}
$("cases").addEventListener("change",load);$("reload").addEventListener("click",load);
$("stop").addEventListener("click",()=>controller?.abort());$("fit").addEventListener("click",fit);
$("zoom").addEventListener("input",e=>{scale=Number(e.target.value)/100;applyScale();});
$("labels").addEventListener("change",()=>{if(nodes.size)renderCanvas();});
$("expand-all").addEventListener("click",()=>{$("tree").querySelectorAll("details").forEach(d=>d.open=true);});
$("collapse-all").addEventListener("click",()=>{$("tree").querySelectorAll("details").forEach(d=>d.open=d.classList.contains("root"));});
try{
  const data=await request("/api/cases");
  const groups=new Map();
  for(const c of data.cases){
    const parts=c.name.split("/"),name=parts.pop(),directory=parts.join("/")||".";
    if(!groups.has(directory)){const group=document.createElement("optgroup");group.label=directory;groups.set(directory,group);$("cases").append(group);}
    const option=document.createElement("option");option.value=c.id;option.textContent=name;groups.get(directory).append(option);
  }
  if(data.cases.length)await load();else{status("所选目录中没有 XML 文件","error");$("reload").disabled=true;}
}catch(error){status(error.message,"error");}
