/* Apply the saved palette before the page paints. Storage is optional. */
(() => {
  const themes = [
    {id:'editor',name:'Editor Dark',description:'Charcoal panels, blue navigation, purple actions, teal charts and amber numbers.',hue:220,chroma:0.12,color:'#1e1e1e',palette:{canvas:'#1e1e1e',surface:'#252526',elevated:'#2d2d30',border:'#414145',text:'#e1e1e6',muted:'#afb2bf',nav:'#75bfff',action:'#d6a0e4',chart:'#56d4c0',number:'#e8d995',label:'#9cdcfe',good:'#b5d99b',warning:'#edc785',manual:'#e4a179'}},
    {id:'neon',name:'Neon Night',description:'Inky blue surfaces with periwinkle, pink, aqua and gold highlights.',hue:230,chroma:0.3,color:'#171a2b',palette:{canvas:'#171a2b',surface:'#20243a',elevated:'#292e47',border:'#414765',text:'#dce3ff',muted:'#a7b0ce',nav:'#9aaeff',action:'#ed9cdb',chart:'#6edbd3',number:'#edca85',label:'#9acdf5',good:'#a8dc99',warning:'#f0bf7a',manual:'#eea28c'}},
    {id:'pastel',name:'Soft Pastel',description:'Smoky surfaces with lavender, coral, mint and butter-yellow highlights.',hue:270,chroma:0.15,color:'#242329',palette:{canvas:'#242329',surface:'#2d2c34',elevated:'#37353f',border:'#514e5e',text:'#eeeaf3',muted:'#bcb4c7',nav:'#b6b7f8',action:'#f2b3cf',chart:'#9de0cd',number:'#eee0a4',label:'#a9cfe8',good:'#b8d8a0',warning:'#eacb96',manual:'#ecb49b'}},
    {id:'daylight',name:'Daylight',description:'Warm white canvas, crisp cards, ink-blue navigation and rich, readable metric colors.',hue:215,chroma:.5,color:'#f5f6f8',palette:{canvas:'#f5f6f8',surface:'#ffffff',elevated:'#eef1f6',border:'#d4dce7',text:'#1c293b',muted:'#526177',nav:'#245bb5',action:'#7441a5',chart:'#08796c',number:'#8b610b',label:'#326184',good:'#35712e',warning:'#955915',manual:'#a64d25'}},
  ];
  const key='form-color-theme';
  function apply(id,persist=true) {
    const theme=themes.find(t=>t.id===id)||themes[0];
    document.documentElement.dataset.theme=theme.id;
    document.documentElement.dataset.themeStyle=theme.palette?'editor':'single';
    if(theme.palette){for(const [role,color] of Object.entries(theme.palette))document.documentElement.style.setProperty('--syntax-'+role,color);}
    const meta=document.querySelector('meta[name="theme-color"]');
    if(meta)meta.content=theme.color;
    if(persist){try{localStorage.setItem(key,theme.id);}catch{}}
    return theme.id;
  }
  let saved;
  try{saved=localStorage.getItem(key);}catch{}
  apply(saved,false);
  window.FormTheme={themes,apply,key};
  window.addEventListener('storage',event=>{if(event.key===key)apply(event.newValue,false);});
})();
