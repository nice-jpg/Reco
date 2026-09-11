import test from "node:test";
import assert from "node:assert/strict";
import {rectangle,extent,traverse,hitTest} from "../static/core.mjs";

test("negative bounds extend left/up; inverted and missing geometry remain distinguishable",()=>{
  const nodes=new Map([[0,{bounds:[0,0,1080,2400]}],[1,{bounds:[-200,-350,20,30]}],[2,{bounds:null}]]);
  assert.deepEqual(extent(nodes,0),{x:-200,y:-350,width:1280,height:2750});
  assert.deepEqual(rectangle([20,30,-10,15]),{x:-10,y:15,width:30,height:15,invalid:true});
  assert.equal(rectangle([1,1,1,3]).width,1);
  assert.equal(rectangle([NaN,0,1,2]),null);
  assert.equal(rectangle(null),null);
});

test("transparent overlay containers do not steal smaller node hits",()=>{
  const nodes=new Map([[0,{id:0,depth:0,bounds:[0,0,100,100]}],[1,{id:1,depth:1,bounds:[10,10,20,20]}],
    [2,{id:2,depth:2,bounds:[10,10,20,20]}],[3,{id:3,depth:1,bounds:[0,0,90,90]}]]);
  assert.equal(hitTest(nodes,15,15),2);
  assert.equal(hitTest(nodes,95,95),0);
  assert.equal(hitTest(nodes,-1,-1),null);
});

test("traversal follows root-to-leaf and all view/text cursors using only public calls",async()=>{
  const calls=[];
  const initial={id:0,bounds:[0,0,100,100],summary:"page",regions:[{id:1}],next_offset:1};
  async function call(name,args){
    calls.push([name,args]);
    if(name==="page_view"){
      if(args.key===0)return {regions:[{id:2}]};
      return {id:args.key,bounds:[-10,0,20,30],summary:"text",regions:[]};
    }
    if(name==="page_node")return {id:args.key,bounds:[-10,0,20,30],summary:"text"};
    if(name==="page_read"){
      if(args.key===2)return {entries:[{item:2,type:"text",value:"B",char_range:[0,1]}]};
      if(!args.char_offset)return {entries:[{item:1,type:"text",value:"🧪",char_range:[0,1]}],next:{offset:0,char_offset:1}};
      const entries=[{item:1,type:"text",value:"中文",char_range:[1,3]}];
      if(args.key===0)entries.push({item:2,type:"text",value:"B",char_range:[0,1]});
      return {entries};
    }
    assert.fail("Unexpected non-public call");
  }
  const nodes=await traverse(call,initial);
  assert.deepEqual([...nodes.keys()],[0,1,2]);
  assert.deepEqual(nodes.get(0).children,[1,2]);
  assert.equal(nodes.get(0).ownText,"");
  assert.equal(nodes.get(1).ownText,"🧪中文");
  assert.equal(nodes.get(2).ownText,"B");
  assert.ok(calls.findIndex(([n,a])=>n==="page_read"&&a.key===0)<calls.findIndex(([n,a])=>n==="page_view"&&a.key===1));
});

test("cycles and non-advancing pagination are rejected",async()=>{
  const initial={id:0,bounds:[0,0,1,1],summary:"page",regions:[{id:0}]};
  const call=async name=>name==="page_node"?{id:0}:{entries:[]};
  await assert.rejects(traverse(call,initial),/循环/);
  const paged={...initial,regions:[],next_offset:1};
  await assert.rejects(traverse(async()=>({regions:[],next_offset:1}),paged),/分页没有前进/);
});
