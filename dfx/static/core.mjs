// Pure helpers and a public-interface-only traversal, shared with tests.
export function rectangle(bounds) {
  if (!Array.isArray(bounds) || bounds.length !== 4 || !bounds.every(Number.isFinite)) return null;
  const [x1,y1,x2,y2] = bounds;
  return {x:Math.min(x1,x2),y:Math.min(y1,y2),width:Math.max(1,Math.abs(x2-x1)),
    height:Math.max(1,Math.abs(y2-y1)),invalid:x2<=x1 || y2<=y1};
}

export function extent(nodes, margin=40) {
  const boxes = [...nodes.values()].map(n=>rectangle(n.bounds)).filter(Boolean);
  const x = Math.min(0,...boxes.map(b=>b.x))-margin;
  const y = Math.min(0,...boxes.map(b=>b.y))-margin;
  const right = Math.max(1,...boxes.map(b=>b.x+b.width))+margin;
  const bottom = Math.max(1,...boxes.map(b=>b.y+b.height))+margin;
  return {x,y,width:right-x,height:bottom-y};
}

export function hitTest(nodes,x,y){
  return [...nodes.values()].map(node=>({node,b:rectangle(node.bounds)}))
    .filter(({b})=>b && x>=b.x && y>=b.y && x<=b.x+b.width && y<=b.y+b.height)
    .sort((a,b)=>a.b.width*a.b.height-b.b.width*b.b.height || b.node.depth-a.node.depth)[0]?.node.id ?? null;
}

export async function traverse(call, initial, progress=()=>{}) {
  const nodes = new Map();
  async function visit(id, parent, depth, first=null) {
    if (nodes.has(id)) throw new Error(`重复/循环区域 ${id}`);
    const node = {id,parent,depth,children:[],entries:[],ownText:""};
    nodes.set(id,node);
    let page = first || await call("page_view",{key:id});
    node.summary=page.summary; node.bounds=page.bounds;
    const seenOffsets=new Set();
    for (;;) {
      node.children.push(...page.regions.map(r=>r.id));
      if (page.next_offset == null) break;
      if (seenOffsets.has(page.next_offset)) throw new Error("结构分页没有前进");
      seenOffsets.add(page.next_offset);
      page=await call("page_view",{key:id,offset:page.next_offset});
    }
    node.details=await call("page_node",{key:id});
    let cursor={},seenCursors=new Set(),items=new Map();
    for (;;) {
      const response=await call("page_read",{key:id,limit:50,max_chars:4096,...cursor});
      for(const entry of response.entries) {
        const existing=items.get(entry.item);
        if ((existing?Array.from(existing.value).length:0) !== entry.char_range[0]) throw new Error("文本字符区间不连续");
        if (existing) existing.value+=entry.value;
        else items.set(entry.item,{item:entry.item,type:entry.type,value:entry.value});
      }
      if (!response.next) break;
      const signature=JSON.stringify(response.next);
      if(seenCursors.has(signature)) throw new Error("文本分页没有前进");
      seenCursors.add(signature); cursor=response.next;
    }
    node.entries=[...items.values()]; progress(nodes);
    for(const child of node.children) await visit(child,id,depth+1);
    // The public read API includes descendants. Avoid painting the same item
    // repeatedly on all ancestors; retain full regional content in the inspector.
    const inherited=new Set(node.children.flatMap(c=>nodes.get(c).entries.map(e=>e.item)));
    node.ownText=node.entries.filter(e=>!inherited.has(e.item) && e.type==="text").map(e=>e.value).join(" ");
  }
  await visit(initial.id,null,0,initial);
  return nodes;
}
