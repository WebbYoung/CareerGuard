import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../static/company.js',import.meta.url),'utf8');
class Element{
 constructor(dataset={}){this.dataset=dataset;this.children=[];this.attributes={};this.hidden=false;this.classList={toggle:()=>{}};}
 setAttribute(k,v){this.attributes[k]=v;}
 removeAttribute(k){delete this.attributes[k];}
 append(...children){this.children.push(...children);}
 prepend(...children){this.children.unshift(...children);}
 replaceChildren(...children){this.children=children;}
}
function fixture(){
 const keys=['overview','jobs','publish','candidates','mail'];
 const panels=keys.map(companyView=>new Element({companyView})),nav=keys.map(companyNav=>{const a=new Element({companyNav});a.orbit=new Element();a.querySelector=()=>a.orbit;return a;}),brand=new Element(),title=new Element(),location={pathname:'/company/jobs'},history=[];
 const document={querySelectorAll:s=>s==='[data-company-view]'?panels:nav,querySelector:s=>s==='.company-sidebar .site-brand'?brand:title,createElementNS:(_,tag)=>new Element({tag})};
 const context={$:s=>document.querySelector(s),document,location,history:{pushState:(_,__,url)=>history.push(url)}};
 vm.createContext(context);const routing=source.slice(source.indexOf('function page()'),source.indexOf('function reset()'));vm.runInContext(routing,context);
 return {...context,panels,nav,brand,title,history};
}
test('company navigation preserves unsaved form state and displays only selected page',()=>{
 const f=fixture();f.panels[2].draft='未提交的岗位';f.show(f.page(),false);
 assert.deepEqual(f.panels.filter(p=>!p.hidden).map(p=>p.dataset.companyView),['jobs']);
 assert.equal(f.nav[1].attributes['aria-current'],'page');
 f.show('publish');assert.equal(f.history.at(-1),'/company/publish');assert.equal(f.panels[2].draft,'未提交的岗位');
 f.show('toString',false);assert.equal(f.panels[0].hidden,false);
});
test('company icon mounting supplies SVG uses recognized by the existing glass atlas',()=>{
 const f=fixture();assert.equal(typeof f.mountIcons,'function','company glass icon mount is missing');f.mountIcons();
 for(const a of f.nav){assert.equal(a.orbit.children[0].dataset.tag,'svg');assert.match(a.orbit.children[0].children[0].attributes.href,/^#i-(grid|list|upload|user|file)$/);}
 assert.equal(f.brand.children[0].children[0].attributes.href,'#i-shield');
});

test('refresh clears previously opened resume before checking current authorization, including failures',async()=>{
 const list=new Element();list.append(new Element({resume:'previously-authorized'}));
 const context={$:()=>list,el:(_,text)=>({textContent:text}),candidateData:{items:[{resume:'private'}],jobs:[]},api:async()=>{throw Error('权限已失效');}};
 vm.createContext(context);vm.runInContext(source.slice(source.indexOf('async function refresh()'),source.indexOf('async function start()')),context);
 await assert.rejects(context.refresh(),/权限已失效/);
 assert.equal(context.candidateData.items.length,0);
 assert.equal(list.children.length,1);
 assert.match(list.children[0].textContent,/校验/);
 assert.equal(list.children[0].dataset,undefined);
});
