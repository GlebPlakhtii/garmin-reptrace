import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const script=fs.readFileSync(new URL('../../src/reptrace/web/static/theme.js',import.meta.url),'utf8');
function setup(saved=null,blocked=false){
 const savedValues=new Map(saved?[['form-color-theme',saved]]:[]),listeners={};
 const meta={};const context={document:{documentElement:{dataset:{},style:{setProperty(key,value){this[key]=value}}},querySelector:()=>meta},localStorage:{getItem:key=>{if(blocked)throw Error('Blocked');return savedValues.get(key)},setItem:(key,value)=>{if(blocked)throw Error('Blocked');savedValues.set(key,value)}},window:{addEventListener:(name,callback)=>listeners[name]=callback}};
 vm.runInNewContext(script,context);
 return {context,savedValues,listeners,meta};
}
test('saved palette restores before rendering and each choice persists',()=>{
 const {context,savedValues,meta}=setup('neon');
 assert.equal(context.document.documentElement.dataset.theme,'neon');
 assert.equal(context.window.FormTheme.themes.length,4);
 for(const theme of context.window.FormTheme.themes){
  context.window.FormTheme.apply(theme.id);
  assert.equal(savedValues.get('form-color-theme'),theme.id);
  assert.equal(context.document.documentElement.dataset.theme,theme.id);
  assert.equal(meta.content,theme.color);
 }
});
test('unavailable storage and invalid saved palettes still produce a usable default',()=>{
 for(const state of [setup('invalid'),setup(null,true)]){
  assert.equal(state.context.document.documentElement.dataset.theme,'editor');
  assert.equal(state.context.window.FormTheme.apply('neon'),'neon');
 }
});
test('palette changes from another tab update without writing back',()=>{
 const {context,listeners,savedValues}=setup('editor');
 listeners.storage({key:'form-color-theme',newValue:'pastel'});
 assert.equal(context.document.documentElement.dataset.theme,'pastel');
 assert.equal(savedValues.get('form-color-theme'),'editor');
});

test('editor palettes use distinct roles with readable foreground contrast',()=>{
 const {context}=setup();
 const luminance=hex=>{const c=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=0.04045?x/12.92:((x+0.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
 const contrast=(a,b)=>{const values=[luminance(a),luminance(b)].sort((x,y)=>y-x);return (values[0]+.05)/(values[1]+.05);};
 for(const theme of context.window.FormTheme.themes.filter(t=>t.palette)){
  const p=theme.palette;
  assert.equal(new Set([p.nav,p.action,p.chart,p.number,p.manual]).size,5);
  for(const role of ['text','muted','nav','action','chart','number','label','good','warning','manual']){
   assert.ok(contrast(p[role],p.surface)>=4.5,`${theme.id}: ${role} contrast`);
  }
  context.window.FormTheme.apply(theme.id);
  assert.equal(context.document.documentElement.dataset.themeStyle,'editor');
  assert.equal(context.document.documentElement.style['--syntax-chart'],p.chart);
 }
 context.window.FormTheme.apply('forest');
 assert.equal(context.document.documentElement.dataset.themeStyle,'editor');
});

test('Garmin editor surfaces and badges use theme colors with readable contrast',()=>{
 const css=fs.readFileSync(new URL('../../src/reptrace/web/static/styles.css',import.meta.url),'utf8');
 assert.match(css,/\.garmin-group\{[^}]*background:var\(--white\)/);
 assert.match(css,/\.garmin-shared-badge\{[^}]*background:var\(--green\);color:var\(--dark\)/);
 assert.match(css,/\.garmin-editor \.dialog-heading p\{color:var\(--muted\)/);
 const {context}=setup();
 const luminance=hex=>{const c=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=0.04045?x/12.92:((x+0.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
 const contrast=(a,b)=>{const values=[luminance(a),luminance(b)].sort((x,y)=>y-x);return (values[0]+.05)/(values[1]+.05);};
 for(const theme of context.window.FormTheme.themes.filter(t=>t.palette)){
  assert.ok(contrast(theme.palette.text,theme.palette.surface)>=4.5,theme.id+' card text');
  assert.ok(contrast(theme.palette.nav,theme.palette.canvas)>=4.5,theme.id+' group number');
 }
});

test('retired single-color themes fall back to Editor Dark',()=>{
 for(const id of ['graphite','midnight','violet','forest','amber']){
  const {context}=setup(id);
  assert.equal(context.document.documentElement.dataset.theme,'editor');
  assert.ok(context.window.FormTheme.themes.every(t=>t.palette));
 }
});

test('Daylight restores and uses readable data inks and button text on white',()=>{
 const {context}=setup('daylight');assert.equal(context.document.documentElement.dataset.theme,'daylight');
 const css=fs.readFileSync(new URL('../../src/reptrace/web/static/styles.css',import.meta.url),'utf8');
 const block=css.match(/:root\[data-theme="daylight"\]\{([^}]+)\}/)[1];
 const colors=[...block.matchAll(/--(?:metric-[\w-]+|series-\d+):(#\w{6})/g)].map(m=>m[1]);
 const luminance=hex=>{const c=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
 assert.ok(colors.length>=20);
 for(const color of colors)assert.ok(1.05/(luminance(color)+.05)>=4.5,color+' white contrast');
 const theme=context.window.FormTheme.themes.find(t=>t.id==='daylight');
 assert.ok(1.05/(luminance(theme.palette.action)+.05)>=4.5);
});
