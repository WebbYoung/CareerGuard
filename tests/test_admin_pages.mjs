import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const require=createRequire(import.meta.url),router=require('../static/admin-pages.js');
const source=readFileSync(new URL('../static/admin-pages.js',import.meta.url),'utf8');
class Element{
  constructor(data={}){this.dataset=data;this.children=[];this.attributes={};this.hidden=false;this.classes=new Set();this.classList={toggle:(name,on)=>on?this.classes.add(name):this.classes.delete(name)};this.handlers={};}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(name,value){this.attributes[name]=value;}
  removeAttribute(name){delete this.attributes[name];}
  addEventListener(name,fn){this.handlers[name]=fn;}
  focus(){this.focused=true;}
}
function fixture(href='http://local/admin?page=users'){
  const nav=new Element(),main=new Element(),nodes=Object.fromEntries(['admin-page-title','admin-page-description','admin-page-eyebrow','admin-breadcrumb'].map(id=>[id,new Element()]));
  const panels=Object.keys(router.pages).map(page=>new Element({adminPage:page}));
  const modelsHost=new Element({adminPage:'models knowledge'});panels.push(modelsHost);
  const location=new URL(href),events={},entries=[];
  const document={title:'',querySelector:()=>nav,querySelectorAll:selector=>selector==='[data-admin-page]'?panels:nav.children,createElement:()=>new Element(),createElementNS:()=>new Element(),getElementById:id=>id==='admin-main'?main:nodes[id]};
  const history=Object.fromEntries(['pushState','replaceState'].map(method=>[method,(_,__,url)=>{entries.push({method,url});location.href=new URL(url,location).href;}]));
  const window={addEventListener:(name,fn)=>events[name]=fn,scrollTo:()=>{}};
  vm.runInNewContext(source,{window,document,location,history,URL});
  return {api:window.AdminPages,nav,panels,modelsHost,document,location,history,events,entries,nodes};
}
test('all nine direct links resolve; unknown and inherited object keys safely fall back',()=>{
  assert.equal(Object.keys(router.pages).length,9);
  for(const name of Object.keys(router.pages))assert.equal(router.resolve('/admin?page='+name),name);
  for(const name of ['bad','toString','__proto__'])assert.equal(router.resolve('/admin?page='+name),'overview');
  assert.equal(router.resolve('/admin#admin-security'),'security');
  assert.equal(router.resolve('/admin?page=users#admin-security'),'users');
  assert.equal(router.pageURL('/admin?source=bookmark#old','knowledge'),'/admin?source=bookmark&page=knowledge');
});
test('direct load shows one page, real navigation links and correct active title',()=>{
  const f=fixture();f.api.init();
  assert.deepEqual(f.panels.filter(p=>!p.hidden).map(p=>p.dataset.adminPage),['users']);
  assert.equal(f.nav.children.length,9);
  assert.equal(f.nav.children.find(l=>l.dataset.adminRoute==='users').attributes['aria-current'],'page');
  assert.equal(f.document.title,'用户管理 · 职安管理控制台');
  for(const link of f.nav.children){assert.match(link.href,/^\/admin\?page=/);assert.equal(link.children[0].children[0].attributes.href,'#i-'+router.pages[link.dataset.adminRoute][3]);}
});
test('navigation preserves nodes and form state, while back/forward restores route and title',()=>{
  const f=fixture();f.api.init();f.panels[1].unsavedInput='保留编辑';
  f.api.go('knowledge');
  assert.equal(f.location.search,'?page=knowledge');assert.equal(f.modelsHost.hidden,false);
  assert.equal(f.panels.find(p=>p.dataset.adminPage==='models').hidden,true);
  assert.equal(f.panels.find(p=>p.dataset.adminPage==='knowledge').hidden,false);
  assert.equal(f.entries.at(-1).method,'pushState');
  f.location.href='http://local/admin?page=users';f.events.popstate();
  assert.equal(f.panels[1].hidden,false);assert.equal(f.panels[1].unsavedInput,'保留编辑');
  assert.equal(f.nodes['admin-page-title'].textContent,'用户管理');assert.equal(f.nodes['admin-page-title'].focused,true);
  f.location.href='http://local/admin?page=models';f.events.popstate();
  assert.equal(f.panels.find(p=>p.dataset.adminPage==='knowledge').hidden,true);
  assert.equal(f.panels.find(p=>p.dataset.adminPage==='models').hidden,false);
});
test('normal clicks route locally; modifier clicks keep native new-tab behavior',()=>{
  const f=fixture();f.api.init();const link=f.nav.children.find(l=>l.dataset.adminRoute==='reviews');let prevented=false;
  const event={target:{closest:()=>link},button:0,preventDefault:()=>prevented=true};
  f.nav.handlers.click({...event,ctrlKey:true});assert.equal(prevented,false);assert.equal(f.location.search,'?page=users');
  f.nav.handlers.click(event);assert.equal(prevented,true);assert.equal(f.location.search,'?page=reviews');
});
test('initial invalid routes are normalized without an extra history entry; init is idempotent',()=>{
  const f=fixture('http://local/admin?page=missing#old');f.api.init();f.api.init();
  assert.equal(f.location.search,'?page=overview');assert.equal(f.location.hash,'');
  assert.equal(f.entries.length,1);assert.equal(f.entries[0].method,'replaceState');assert.equal(f.nav.children.length,9);
});
