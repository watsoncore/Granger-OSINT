"""Fixed, read-only DOM inspection for the isolated native QA surface."""

GRAPH_LAYOUT_INSPECTION = r"""function(){
  const g=document.querySelector('[data-graph-layout]'); if(!g)return null;
  const raw=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}};
  const rect=e=>{
    const r=raw(e);let left=r.x,top=r.y,right=r.x+r.width,bottom=r.y+r.height;
    for(let p=e.parentElement;p;p=p.parentElement){
      const s=getComputedStyle(p),b=raw(p);
      if(/auto|scroll|hidden|clip/.test(s.overflowX)){left=Math.max(left,b.x);right=Math.min(right,b.x+b.width)}
      if(/auto|scroll|hidden|clip/.test(s.overflowY)){top=Math.max(top,b.y);bottom=Math.min(bottom,b.y+b.height)}
      if(p===g)break;
    }
    return {x:left,y:top,width:Math.max(0,right-left),height:Math.max(0,bottom-top)};
  };
  const visible=e=>{
    if(e.closest('[hidden]'))return false;
    for(let p=e.parentElement;p;p=p.parentElement){if(p.tagName==='DETAILS'&&!p.open&&!p.querySelector('summary')?.contains(e))return false;if(p===g)break}
    const r=rect(e);return r.width>1&&r.height>1&&getComputedStyle(e).visibility!=='hidden';
  };
  const selectors=['.research-title','.graph-command-bar','.canvas-tool-rail','.canvas-view-switch','.canvas-corner-controls','.canvas-bottom-controls','.canvas-selection-toolbar','.canvas-overview','.graph-overview','.canvas-focus','.canvas-activity','.graph-analysis-index','.research-inspector','.results-drawer','.research-insertion-result'];
  const boxes=selectors.flatMap(s=>[...g.querySelectorAll(s)].filter(visible).map(e=>({name:e.className,...rect(e)})));
  const canvas=g.querySelector('.investigation-graph-canvas');
  try{const map=JSON.parse(canvas?.dataset.minimap||'null');if(map){const c=raw(canvas);boxes.push({name:'minimap',x:c.x+map.x,y:c.y+map.y,width:map.width,height:map.height})}}catch{}
  const overlap=(a,b)=>{const w=Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x),h=Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y);return w>2&&h>2?{a:a.name,b:b.name,width:w,height:h}:null};
  const overlaps=[];for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){const hit=overlap(boxes[i],boxes[j]);if(hit)overlaps.push(hit)}
  const controls=[...g.querySelectorAll('button,summary,input:not([type=range])')].filter(e=>visible(e)&&!e.closest('details[open]>div,.research-context,[role=menu],[role=dialog],.canvas-modal-shade'));
  const controlOverlaps=[];
  for(let i=0;i<controls.length;i++)for(let j=i+1;j<controls.length;j++){
    const a=controls[i],b=controls[j];if(a.contains(b)||b.contains(a))continue;
    const hit=overlap({name:a.getAttribute('aria-label')||a.textContent.slice(0,60),...rect(a)},{name:b.getAttribute('aria-label')||b.textContent.slice(0,60),...rect(b)});if(hit)controlOverlaps.push(hit);
  }
  const clippedControls=controls.filter(e=>{const a=raw(e),b=rect(e);return b.width<a.width-3}).map(e=>({name:e.getAttribute('aria-label')||e.textContent.slice(0,60),raw:raw(e),visible:rect(e)}));
  const commandControls=[...g.querySelectorAll('.graph-command-search,.graph-command-type>.searchable-select,.graph-command-bar .research-filters>summary,.graph-command-layout>.searchable-select')].filter(visible).map(e=>({name:e.getAttribute('aria-label')||e.className,...raw(e)}));
  const popups=[...document.querySelectorAll('[data-radix-popper-content-wrapper],.research-filters[open]>div,.research-project-menu[open]>div,.research-context')].filter(visible).map(e=>({name:e.className,...raw(e)}));
  const popupOverflow=popups.filter(r=>r.x<0||r.y<0||r.x+r.width>innerWidth+2||r.y+r.height>innerHeight+2);
  return {style:g.dataset.graphStyle,root:raw(g),boxes,overlaps,controlOverlaps,clippedControls,commandControls,popupOverflow,
    icons:[...document.querySelectorAll('[data-crypto-icon]')].map(i=>({id:i.dataset.cryptoIcon,loaded:i.complete&&i.naturalWidth>0,width:i.width})),dpr:devicePixelRatio};
}"""
