import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {recoveryPage,recoveryReview} from '../../src/reptrace/web/static/recovery.mjs';

const pending={id:'123',kind:'correction',activityId:'demo-1',status:'local_pending',destination:'both',remoteStatus:'saved',localStatus:'pending',canResume:true,preview:'Bench: 40 → 42.5 kg'};
test('status list covers empty, error, and partially completed operations',()=>{
  assert.match(recoveryPage({operations:[]}),/No saved operations yet/);
  const html=recoveryPage({operations:[pending],error:'Offline'});
  assert.match(html,/Last loaded status is shown below/);
  assert.match(html,/1 need attention/);
  assert.match(html,/Saved and checked/);
  assert.match(html,/Review recovery/);
});
test('recovery review escapes stored text and never offers to start an unconfirmed preview',()=>{
  const html=recoveryReview({...pending,preview:'<script>alert("bad")</script>'});
  assert.doesNotMatch(html,/<script>/);
  assert.match(html,/&lt;script&gt;/);
  assert.match(html,/Check and continue/);
  for(const status of ['preview','done','cancelled']){
    assert.doesNotMatch(recoveryReview({...pending,status}),/data-operation-resume/);
  }
  assert.match(recoveryReview({...pending,destination:'local'}),/Garmin will not be changed/);
});
test('creation status distinguishes unselected workouts and delivery requests from watch sync',()=>{
  const html=recoveryPage({operations:[{...pending,kind:'creation',items:[
    {name:'Upper',selected:true,creation:'saved',delivery:'requested'},
    {name:'Lower',selected:false,creation:'not_started',delivery:'not_started'},
  ]}]});
  assert.match(html,/Delivery requested/);
  assert.match(html,/does not confirm watch sync/);
  assert.match(html,/Not selected/);
});

const source=fs.readFileSync(new URL('../../src/reptrace/web/static/app.js',import.meta.url),'utf8');
function app(fetch){
  const nodes=new Map();
  const context={fetch,AbortSignal,renderOperationHistory:recoveryPage,recoveryReview,document:{querySelector:key=>{
    if(!nodes.has(key))nodes.set(key,{innerHTML:'',open:false,showModal(){this.open=true;}});
    return nodes.get(key);
  }},window:{},setTimeout,clearTimeout};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('\n')+1,source.indexOf("document.addEventListener('click'"))+`
    render=()=>{};toast=()=>{};load=()=>{};
    this.app={state,operationsPage,loadOperationHistory,reviewOperation,continueOperation};
  `,context);
  return {...context.app,nodes};
}
test('opening status and reviewing are local reads; continuation sends only the saved identity',async()=>{
  const requests=[];
  const a=app(async(url,options)=>{
    requests.push({url,options});
    return {ok:true,json:async()=>url.includes('?id=')?pending:url==='/api/garmin-workouts'?{...pending,status:'done',canResume:false}:{operations:[pending]}};
  });
  await a.loadOperationHistory();
  await a.reviewOperation('123');
  assert.ok(requests.every(r=>!r.options.method));
  assert.equal(a.state.data,null);
  assert.match(a.operationsPage(),/Review recovery/);
  await a.continueOperation('123');
  const posts=requests.filter(r=>r.options.method==='POST');
  assert.equal(posts.length,1);
  assert.deepEqual(JSON.parse(posts[0].options.body),{operation:'integration_resume',requestId:'123'});
  assert.equal(a.state.operationReview.status,'done');
  assert.equal(a.state.operationSaving,false);
});
test('late history responses cannot overwrite a newer status and failures retain the last snapshot',async()=>{
  const pendingRequests=[];
  const a=app(()=>new Promise(resolve=>pendingRequests.push(resolve)));
  const old=a.loadOperationHistory(),fresh=a.loadOperationHistory();
  pendingRequests[1]({ok:true,json:async()=>({operations:[{...pending,status:'done'}]})});await fresh;
  pendingRequests[0]({ok:true,json:async()=>({operations:[pending]})});await old;
  assert.equal(a.state.operations[0].status,'done');
  const failed=a.loadOperationHistory();
  pendingRequests[2]({ok:false,json:async()=>({error:'Unavailable'})});await failed;
  assert.equal(a.state.operations[0].status,'done');
  assert.equal(a.state.operationsError,'Unavailable');
});
test('double activation cannot send a second recovery request',async()=>{
  let finish,posts=0;
  const a=app((url,options)=>{
    if(options.method==='POST'){posts++;return new Promise(resolve=>finish=resolve);}
    return Promise.resolve({ok:true,json:async()=>({operations:[]})});
  });
  a.state.operationReview=pending;
  const first=a.continueOperation('123');
  await a.continueOperation('123');
  assert.equal(posts,1);
  finish({ok:true,json:async()=>({...pending,status:'done',canResume:false})});await first;
});
