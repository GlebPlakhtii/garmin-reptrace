import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html=readFileSync(new URL('../../src/reptrace/telegram/workout_widget.html',import.meta.url),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const sample={v:1,title:'Synthetic session',date:'2026-11-10',summary:'9 sets · 72 reps',volume:'1500 kg·reps',coverage:'8/9 sets with volume',e:0,p:0,ec:2,pc:2,exercise:'Press',count:6,rows:[['0','8'],['—','—'],['20','8'],['20','8']]};

function setup(data=sample){
 const nodes={},events={},requests=[];
 function node(){return {textContent:'',disabled:false,hidden:false,children:[],handlers:{},appendChild(child){this.children.push(child);},addEventListener(type,fn){this.handlers[type]=fn;},set innerHTML(_){throw Error('Use textContent for untrusted data');}};}
 for(const match of html.matchAll(/id="([^"]+)"/g))nodes[match[1]]=node();
 let answer=async()=>({result:JSON.stringify({...sample,e:1})});
 const widget={chatData:JSON.stringify(data),onEvent:(type,fn)=>events[type]=fn,ready(){},request(value){requests.push(value);return answer(value);}};
 vm.runInNewContext(script,{TelegramWidget:widget,document:{getElementById:id=>nodes[id],createElement:()=>node()}});
 return {nodes,widget,events,requests,answer(fn){answer=fn;},click(id){if(!nodes[id].disabled)nodes[id].handlers.click();}};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('widget shows private data as text and expands recorded sets with explicit missing values',()=>{
 const app=setup({...sample,exercise:'<img src=x onerror=bad()>'});
 assert.equal(app.nodes.exercise.textContent,'<img src=x onerror=bad()>');
 assert.equal(app.nodes.previous.disabled,true);
 assert.equal(app.nodes.sets.hidden,true);
 app.click('toggle');
 assert.equal(app.nodes.sets.hidden,false);
 assert.equal(app.nodes.toggle.textContent,'Hide sets');
 const row=app.nodes.rows.children[1];
 assert.equal(row.children[1].textContent,'—');
 assert.equal(row.children[2].textContent,'—');
 assert.equal(app.nodes.rows.children[0].children[1].textContent,'0');
});

test('navigation sends one bounded request, handles response and preserves expanded sets',async()=>{
 const app=setup();
 let complete;
 app.answer(()=>new Promise(resolve=>complete=resolve));
 app.click('toggle');app.click('next');app.click('next');
 assert.deepEqual(app.requests,['view:1:0']);
 assert.equal(app.nodes.next.disabled,true);
 complete({result:JSON.stringify({...sample,e:1,exercise:'Row'})});
 await flush();
 assert.equal(app.nodes.exercise.textContent,'Row');
 assert.equal(app.nodes.position.textContent,'Exercise 2 of 2');
 assert.equal(app.nodes.sets.hidden,false);
 assert.equal(app.nodes.previous.disabled,false);
 assert.equal(app.nodes.next.disabled,true);
 app.answer(async()=>({result:JSON.stringify({...sample,e:1,p:1,rows:[['10','5'],['12','6']]})}));
 app.click('more');await flush();
 assert.equal(app.requests[1],'view:1:1');
 assert.equal(app.nodes.page.textContent,'2 / 2');
 assert.equal(app.nodes.more.disabled,true);
});

test('errors retain report data and reenable navigation for retry',async()=>{
 const app=setup();
 for(const answer of [async()=>{throw Error('TIMEOUT');},()=>{throw Error('BUSY');},async()=>({result:'bad JSON'})]){
  app.answer(answer);app.click('next');await flush();
  assert.match(app.nodes.status.textContent,/retry/);
  assert.equal(app.nodes.next.disabled,false);
  assert.equal(app.nodes.title.textContent,sample.title);
 }
 app.answer(async()=>({result:JSON.stringify({error:'Expired. Send /widget.'})}));
 app.click('next');await flush();
 assert.equal(app.nodes.status.textContent,'Expired. Send /widget.');
});

test('pushed private state updates the page, empty and malformed state remain usable',()=>{
 const app=setup();
 app.widget.chatData=JSON.stringify({...sample,e:1});app.events.chatDataChanged();
 assert.equal(app.nodes.position.textContent,'Exercise 2 of 2');
 const empty=setup({...sample,ec:0,count:0,rows:[]});
 assert.equal(empty.nodes.toggle.disabled,true);
 assert.equal(empty.nodes.next.disabled,true);
 const missing=setup(null);
 assert.match(missing.nodes.status.textContent,/unavailable/);
 assert.equal(missing.nodes.next.disabled,true);
});
