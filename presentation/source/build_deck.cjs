const pptxgen = require('pptxgenjs');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const SRC = JSON.parse(fs.readFileSync(path.join(ROOT,'source_content.json'),'utf8'));
const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = '陈奕桥、孙锤笠、罗恪勤、刘宇哲、马愿博';
pptx.subject = '公共财政学：烟花爆竹管制中的工具选择';
pptx.title = '烟花爆竹管制中的工具选择';
pptx.company = '清华大学';
pptx.lang = 'zh-CN';
pptx.theme = {headFontFace:'Microsoft YaHei',bodyFontFace:'Microsoft YaHei',lang:'zh-CN'};
const C = {ink:'24212C',muted:'625D70',purple:'683B83',deep:'342042',lilac:'F2EDF6',soft:'F7F6F9',mid:'B19AC2',light:'DAD0E3',teal:'267E7A',gray:'E7E3EB',white:'FFFFFF',orange:'A84E32'};
const W=13.333333,H=7.5,M=.66;
const bounds=[];
function tx(s,text,x,y,w,h,size=19,opt={}) {
  s.addText(text,{x,y,w,h,fontFace:'Microsoft YaHei',fontSize:size,color:C.ink,margin:0,
    breakLine:false,paraSpaceAfterPt:0,valign:'mid',...opt});
  bounds.push({slide:s._slideNum,text:typeof text==='string'?text.slice(0,35):'[rich]',x,y,w,h});
}
function rect(s,x,y,w,h,fill,opt={}) {s.addShape(pptx.ShapeType.rect,{x,y,w,h,line:{color:fill,transparency:100},fill:{color:fill},...opt});}
function line(s,x1,y1,x2,y2,color=C.gray,width=1) {s.addShape(pptx.ShapeType.line,{x:x1,y:y1,w:x2-x1,h:y2-y1,line:{color,width}});}
function dot(s,x,y,r,fill) {s.addShape(pptx.ShapeType.ellipse,{x:x-r,y:y-r,w:r*2,h:r*2,fill:{color:fill},line:{color:fill,transparency:100}});}
function num(s,value,x,y,w,h=1,size=52,color=C.purple) {tx(s,value,x,y,w,h,size,{fontFace:'Arial',bold:true,color});}
function base(n,section,title,dark=false) {
  const s=pptx.addSlide(); s.background={color:dark?C.deep:C.white};
  tx(s,section,M,.36,11,.27,12,{color:dark?'D2BEDF':C.purple,bold:true});
  tx(s,title,M,.87,12.0,.67,31.5,{bold:true,color:dark?C.white:C.ink});
  tx(s,'公共财政学  ·  烟花爆竹管制中的工具选择',M,7.13,10,.19,9,{color:dark?'CFBED8':'857D8C'});
  tx(s,`${String(n).padStart(2,'0')} / 15`,11.78,7.08,.88,.27,10,{color:dark?'CFBED8':'857D8C',align:'right'});
  let correction='';
  let sourceNote=SRC[n-1].notes;
  let sourceText=SRC[n-1].text;
  if(n===3) {
    sourceText=sourceText.replace('65.3% 的变异在城市 × 年份；全国统一、按年的税率只有一个格子。','探索性分解中，省 × 年与城市 × 年交互项合计 65.3%。全国统一税率可逐年调整，但不能按地区分别设定。');
    sourceNote='40 秒：提出工具设定层级与损害变异的匹配问题。65.3% 是两类交互项的探索性占比，不是因果效应。';
  }
  if(n===6) {
    sourceText='全国统一、全期不变：1 格。全国统一、逐年调整：|T| 格。按城市固定设定：|C| 格。省 × 年设定：|P| × |T| 格。城市 × 年份设定：|C| × |T| 格。格子越贴近损害的空间与时间尺度，越能区分相应单元。L(P)=σ²−Var(E[D|cell]) 表示给定政策单元划分后的未覆盖方差；具体可覆盖份额取决于分解口径。色块为示意。';
    sourceNote='30 秒：全国统一税率若全期不变只有一个格；逐年调整是 |T| 格；城市、地区年度工具有更多单元。设定更细可以区分更多时空变化，但不代表每格都能被准确观测或有效治理。';
  }
  if(n===10) {
    correction='【口径说明】65.3% 是省×年与城市×年交互项之和；若四项分解互斥且穷尽，全国统一逐年工具仍未区分的城市与交互项共 87.3%。这只是描述性方差分解，不是政策因果效果或税率最优性检验。\n\n';
    sourceText=sourceText.replace('65.3% 是全国统一、按年设定工具的缺口上界。它不是税与禁令之间的差距。','65.3% 是省×年与城市×年交互项之和；按四项分解，全国统一逐年工具仍不能区分的城市与交互项共 87.3%。这是描述性分解，不是税与禁令的因果差距。');
    sourceNote='50 秒：四项分解分别是城市间、年份间、省×年和城市×年。后两项合计 65.3%。若全国税率逐年调整，年份项可以区分；城市间与两个交互项合计 87.3% 仍无法区分。不是因果效应。';
  }
  if(n===11) {
    sourceText=sourceText.replace('一个城市的去留改变符号（−36.70 与 +1.12）。','省份×年份设定下，含滨州为 −5.34，剔除后为 +1.12。−36.70 与 +1.12 对应两个不同固定效应设定。');
    sourceNote='50 秒：强调处理状态缺失和政策来源限制。省份×年份设定下，滨州去留对应 −5.34 / +1.12；两个固定效应设定对应 −36.70 / +1.12。MDE 高于典型尖峰，说明统计功效有限。';
  }
  if(n===14) sourceText=sourceText.replace('全国统一、按年的从价税只有一个格子，对不上城市 × 年份的变异。','全国统一的从价税可以按年调整，但无法分别响应各城市的年度变化。');
  s.addNotes(`${correction}${sourceNote}\n\n【原稿内容留存，供演讲与核对】\n${sourceText}`);
  return s;
}
function callout(s,text,y=6.25,size=23,color=C.purple){tx(s,text,M,y,12,.5,size,{bold:true,color});}

// 1. Cover: retain the source campus photograph and university mark.
{
 const s=pptx.addSlide();s.background={color:C.white};
 const cover=path.join(ROOT,'assets/cover-crop.jpg');
 s.addImage({path:cover,x:8.12,y:0,w:5.2133,h:H});
 s.addImage({path:path.join(ROOT,'assets/logo.png'),x:.59,y:.34,w:1.58,h:1.19});
 tx(s,'公共财政学',.77,1.72,6.7,.35,17,{bold:true,color:C.purple});
 tx(s,'烟花爆竹管制中的\n工具选择',.73,2.28,7.05,1.72,39,{bold:true,breakLine:false,lineSpacingMultiple:1.12});
 tx(s,'一个价格工具三十年未校准',.77,4.31,6.9,.55,23,{color:C.purple});
 tx(s,'陈奕桥　孙锤笠　罗恪勤　刘宇哲　马愿博',.77,5.77,6.9,.48,16);
 tx(s,'2026 年 11 月',.77,6.38,5,.3,15,{color:C.muted});
 s.addNotes(SRC[0].notes);
}

// 2. Motivation: three deliberately large, comparable facts.
{
 const s=base(2,'研究动机','价格工具已存在，地方仍叠加禁令');
 const metrics=[
  {x:M,value:'43.1',unit:'μg/m³',label:'初一 PM2.5 较基线',body:'中位数 28.1\n尖峰存在，城际差异大'},
  {x:4.86,value:'15%',unit:'32 年未调',label:'全国从价消费税',body:'1994 年起征\n税率迄今未调整'},
  {x:9.06,value:'6 年',unit:'先加码，后回摆',label:'地方禁放限放政策',body:'数量管制持续变化\n同期税率没有变化'}];
 metrics.forEach(a=>{num(s,a.value,a.x,2.02,3.58,1.03,54);tx(s,a.unit,a.x,3.12,3.58,.38,19,{color:C.purple});tx(s,a.label,a.x,3.85,3.58,.43,21,{bold:true});tx(s,a.body,a.x,4.47,3.58,.9,18,{color:C.muted,breakLine:false});});
 callout(s,'工具都有了，为什么仍难对准损害？',6.19,28);
}

// 3. A matching question rather than a causal-effect claim.
{
 const s=base(3,'研究问题','研究重点：工具与损害的匹配');
 rect(s,M,1.95,5.5,1.2,C.lilac);rect(s,7.17,1.95,5.5,1.2,C.soft);
 tx(s,'X  工具的设定层级与频率',.92,2.14,5,.43,22,{bold:true,color:C.purple});
 tx(s,'Y  尖峰增量的时空变异',7.43,2.14,5,.43,22,{bold:true});
 tx(s,'全国 / 省 / 市  ×  调整频率',.92,2.72,5,.27,16,{color:C.muted});
 tx(s,'城市 × 年份',7.43,2.72,5,.27,16,{color:C.muted});
 tx(s,'匹配',6.24,2.39,.85,.37,18,{bold:true,color:C.purple,align:'center'});
 tx(s,'测量问题',M,3.71,5.7,.4,18,{color:C.purple,bold:true});
 tx(s,'这个税能否校准到边际损害？',M,4.27,5.7,.5,23,{bold:true});
 tx(s,'用方差分解与校准回答。',M,5.0,5.7,.45,19,{color:C.muted});
 tx(s,'政治经济学问题',7.17,3.71,5.5,.4,18,{color:C.purple,bold:true});
 tx(s,'为什么长期没有重新校准？',7.17,4.27,5.5,.5,23,{bold:true});
 tx(s,'成本可见性：一个待验证的假说。',7.17,5.0,5.5,.45,19,{color:C.muted});
 tx(s,'省 × 年与城市 × 年交互项合计 65.3%；这不是政策因果效应。',M,6.23,12,.47,21,{bold:true,color:C.purple});
}

// 4. Literature → gap → contribution.
{
 const s=base(4,'文献与贡献','把“工具选择”变成可计算的匹配问题');
 const cols=[
  {x:M,h:'已有研究',bg:C.soft,c:C.ink,rows:[['春节污染尖峰','Li et al. (2025)\nChen et al. (2022)'],['禁放政策效果','陆卜梵、刘蓓蓓 (2022)'],['政策成本可见性','Beiser-McGrath et al. (2023)']]},
  {x:4.76,h:'尚待回答',bg:C.soft,c:C.ink,rows:[['政策有效吗？','多数研究的核心问题'],['哪一级工具，对准哪一级变异？','工具与损害尺度的匹配'],['每公斤损害是常数吗？','空间、时间差异有待刻画']]},
  {x:8.86,h:'本文贡献',bg:C.lilac,c:C.purple,rows:[['测准时空结构','给出可复算的四级分解'],['报告识别边界','如实展示一次失败的识别'],['提出新工具对','将成本可见性用于税与禁令']]}];
 cols.forEach(a=>{rect(s,a.x,1.93,3.81,4.08,a.bg);tx(s,a.h,a.x+.24,2.15,3.32,.43,24,{bold:true,color:a.c});a.rows.forEach((r,j)=>{tx(s,r[0],a.x+.24,2.91+j*.94,3.32,.5,17.5,{bold:true});tx(s,r[1],a.x+.24,3.42+j*.94,3.32,.42,14.5,{color:C.muted});});});
 callout(s,'贡献在于匹配框架与证据边界。',6.36,23);
}

// 5. Institutional comparison, with the two levels explicit.
{
 const s=base(5,'制度背景','两套工具，两个设定层级');
 rect(s,M,1.87,5.8,4.15,C.lilac);rect(s,6.87,1.87,5.8,4.15,C.soft);
 tx(s,'价格工具  /  国家',.92,2.07,5.27,.45,24,{bold:true,color:C.purple});
 num(s,'15%',.92,2.69,2.3,.8,43);tx(s,'从价征收',3.19,2.89,2.7,.4,20,{bold:true});
 tx(s,'生产、委托加工、进口环节征收；出口免征。',.92,3.66,5.25,.74,18);
 tx(s,'1994 年起征；2006 年“绿色化”调整未触及。',.92,4.47,5.25,.75,18);
 tx(s,'按价格征收，不按火药量征收。',.92,5.36,5.25,.4,18,{bold:true,color:C.purple});
 tx(s,'数量工具  /  城市',7.13,2.07,5.27,.45,24,{bold:true,color:C.teal});
 [['2017','国家要求各市制定禁放限放方案'],['2023','国家方案删去该条，地方自行决定'],['2024','东营：政府令第 208 号 → 全面禁放']].forEach((a,j)=>{tx(s,a[0],7.13,2.92+j*.83,1.0,.4,21,{fontFace:'Arial',bold:true,color:C.teal});tx(s,a[1],8.35,2.87+j*.83,4.05,.64,17.5);});
 tx(s,'34 城取证：23/30 提到，11/30 独立列项。',7.13,5.45,5.25,.35,15.5,{color:C.muted});
 tx(s,'干预理由',M,6.28,1.6,.4,19,{bold:true,color:C.purple});
 tx(s,'清洁空气是公共品；当事人多且分散，私人协商难以实现。',2.34,6.23,10.3,.52,19);
}

// 6. Native PowerPoint cells show the partition used by the loss function.
{
 const s=base(6,'理论框架','解析度：工具能覆盖哪一级变异');
 tx(s,'L(P) = σ² − Var(E[D | cell])',M,1.83,12,.58,28,{fontFace:'Cambria',color:C.purple,align:'center'});
 const levels=[
  {title:'全国统一\n全期不变',count:'1 格',desc:'时间与地区\n都不区分',kind:'all'},
  {title:'全国统一\n逐年调整',count:'|T| 格',desc:'区分年份\n不区分地区',kind:'year'},
  {title:'按城市\n固定设定',count:'|C| 格',desc:'区分城市\n不区分年份',kind:'city'},
  {title:'省份 × 年\n分别设定',count:'|P| × |T| 格',desc:'区分省份\n年度变化',kind:'provinceYear'},
  {title:'城市 × 年\n分别设定',count:'|C| × |T| 格',desc:'区分城市\n年度变化',kind:'cityYear'}];
 const colors=[C.light,C.mid,'9873AE',C.purple];
 levels.forEach((a,k)=>{
  const x=M+k*2.45;
  tx(s,a.title,x,2.62,2.24,.72,18.2,{bold:true,align:'center',breakLine:false});
  for(let r=0;r<4;r++)for(let c=0;c<4;c++){
   let ci=0;
   if(a.kind==='year') ci=c;
   if(a.kind==='city') ci=r;
   if(a.kind==='provinceYear') ci=(Math.floor(r/2)+c)%4;
   if(a.kind==='cityYear') ci=(r+c)%4;
   rect(s,x+.31+c*.42,3.55+r*.34,.38,.29,colors[ci]);
  }
  tx(s,a.count,x,5.05,2.24,.35,19.5,{bold:true,color:C.purple,align:'center'});
  tx(s,a.desc,x,5.58,2.24,.68,16.2,{color:C.muted,align:'center',breakLine:false});
 });
 tx(s,'色块示意政策单元；解析度取决于“损害”与“cell”的具体定义，不等同于识别因果效果。',M,6.55,12,.32,15.4,{color:C.muted,align:'center'});
}

// 7. Distinguish the coverage universe from the analysis samples.
{
 const s=base(7,'数据与变量','389 城、12 个春节窗口，刻画尖峰增量');
 [['389','城市覆盖',M],['12','春节窗口 · 2015—2026',4.76],['3,672','平衡面板 · 306 城 × 12 年',8.86]].forEach(([v,l,x])=>{num(s,v,x,1.86,3.81,.88,48);tx(s,l,x,2.92,3.81,.38,18,{color:C.muted});});
 tx(s,'主结果：初一 PM2.5 − 基线 PM2.5',M,3.72,12,.5,24,{bold:true,color:C.purple});
 const x0=1.15,dx=1.09,y=4.96;
 rect(s,.85,4.55,6.12,.85,C.lilac);
 line(s,x0,y,11.78,y,'AAA1B3',1.5);
 [-7,-6,-5,-4,-3,-2,-1,0,1,2].forEach((d,i)=>{const x=x0+i*dx;dot(s,x,y,d===1?.095:.045,d===1?C.purple:C.mid);tx(s,String(d>0?'+'+d:d),x-.35,5.48,.7,.3,15,{align:'center',color:C.muted});});
 tx(s,'基线窗口：除夕前 7 日至前 2 日',1.03,4.13,6,.3,16,{color:C.purple});
 tx(s,'除夕',8.27,4.37,1,.3,16,{align:'center'});tx(s,'初一',9.36,4.37,1,.3,16,{bold:true,color:C.purple,align:'center'});
 tx(s,'非平衡面板 4,240 城市-年  ·  作图口径 308 城  ·  城市-日 63,515 行',M,6.07,12,.4,16.5,{color:C.muted});
 tx(s,'逐小时指标：PM2.5、PM10、AQI、SO2、NO2、O3、CO；所有数字由脚本产出。',M,6.58,12,.33,15.5,{color:C.muted});
}

// 8. The policy table and estimation choices are editable native objects.
{
 const s=base(8,'研究设计','三批政策变化，构成交错 DID 设计');
 const xs=[M,1.79,3.65,5.45],ws=[1.03,1.76,1.70,2.37];
 ['批次','城市','政策方向','处理单位'].forEach((v,i)=>tx(s,v,xs[i],1.99,ws[i],.34,17,{bold:true,color:C.purple}));
 const rows=[['2023','河南 5 城','禁 → 限','5（二手来源）'],['2024','东营','限 → 禁','1（一手来源）'],['2026','山西 10 城','省级统一退出','1（无同省对照）']];
 rows.forEach((row,r)=>{if(r%2===0)rect(s,M,2.53+r*.91,7.22,.78,C.soft);row.forEach((v,i)=>tx(s,v,xs[i]+.04,2.7+r*.91,ws[i]-.08,.38,16.5,{bold:i===0}));});
 rect(s,8.3,1.87,4.37,3.61,C.lilac);
 tx(s,'估计设定',8.57,2.08,3.8,.44,22,{bold:true,color:C.purple});
 tx(s,'305 城 × 6 年 = 1,830 行\n2021—2026，城市 × 春节年份',8.57,2.77,3.8,.85,17.5);
 tx(s,'城市 + 年份固定效应\n另报省份 × 年份固定效应\n标准误按城市聚类（CR1）',8.57,3.98,3.8,1.04,17);
 tx(s,'组间比较：河南 5 城 vs 省内 12 城；东营 vs 山东其余城市。',M,5.86,12,.46,18);
 callout(s,'估计可以计算，但可信度取决于识别条件。',6.45,23);
}

// 9. Retain the original empirical figure without reconstructing unavailable data.
{
 const s=base(9,'测量结果','初一尖峰：真实、集中、差异大');
 const fig=path.join(ROOT,'assets/event_chart.png');
 s.addImage({path:fig,x:M,y:1.71,w:12.01,h:4.92});
 tx(s,'均值 43.1',M,6.53,3.4,.38,20,{bold:true,color:C.purple});
 tx(s,'中位数 28.1',4.58,6.53,3.5,.38,20,{bold:true,color:C.purple});
 tx(s,'23.3% 的城市-年尖峰为负',8.12,6.53,4.55,.38,18,{bold:true,color:C.purple});
}

// 10. The original four-way decomposition, explicitly separating its two interactions.
{
 const s=base(10,'核心结果：方差分解','65.3% 的变异来自地区与年份的交互');
 num(s,'65.3%',M,1.98,4.6,1.1,64);
 tx(s,'省 × 年 30.1%\n城市 × 年 35.2%',5.78,2.05,6.2,1.0,24,{bold:true,color:C.purple});
 const parts=[{v:22,label:'城市间',sub:'按城市设定',fill:C.light,tc:C.deep},{v:12.7,label:'年份间',sub:'按年调整',fill:C.mid,tc:C.deep},{v:30.1,label:'省 × 年',sub:'省级、逐年',fill:'9873AE',tc:C.white},{v:35.2,label:'城市 × 年',sub:'城市、逐年',fill:C.purple,tc:C.white}];
 let x=M;
 parts.forEach(a=>{const w=12.01*a.v/100;rect(s,x,3.55,w,1.02,a.fill);tx(s,a.v.toFixed(1)+'%',x,3.85,w,.42,24,{fontFace:'Arial',bold:true,color:a.tc,align:'center'});tx(s,a.label,x,4.83,w,.34,19,{bold:true,align:'center'});tx(s,a.sub,x,5.36,w,.31,16,{color:C.muted,align:'center'});x+=w;});
 tx(s,'平衡面板，N = 3,672',M,6.02,12,.28,14,{color:C.muted});
 tx(s,'全国工具若可逐年调整，城市与交互项合计 87.3% 仍未区分。',M,6.49,12,.42,20.5,{bold:true,color:C.purple});
}

// 11. Four evidence limits, each anchored on one diagnostic statistic.
{
 const s=base(11,'因果识别的边界','四层限制，使政策效应难以识别');
 const blocks=[
  {x:M,y:1.91,v:'89%',head:'城市-年没有政策记录',body:'处理变量测不准；“全国对照”\n实际上包含大量无记录城市。'},
  {x:6.87,y:1.91,v:'6',head:'个可用切换单位',body:'5 个仅二手来源；省×年设定下，\n滨州去留对应 −5.34 / +1.12。'},
  {x:M,y:4.02,v:'p = 0.18',head:'随机化推断未过关',body:'初一不显著、无关日显著；\n前置期也不平稳。'},
  {x:6.87,y:4.02,v:'≈ 100',head:'最小可检测效应',body:'单位 μg/m³；大于中位尖峰 28.1。\n当前设计对中等量级变化功效有限。'}];
 blocks.forEach(a=>{rect(s,a.x,a.y,5.8,1.9,C.soft);num(s,a.v,a.x+.23,a.y+.16,2.38,.57,32);tx(s,a.head,a.x+2.71,a.y+.16,2.85,.64,17.5,{bold:true});tx(s,a.body,a.x+.23,a.y+.99,5.34,.68,17.3,{color:C.muted});});
 callout(s,'识别失败 ≠ 禁令无效',6.39,27);
}

// 12. Keep both calibration routes and their uncertainty visible.
{
 const s=base(12,'结果：校准','给不出点估计，但能定位不确定性');
 const tops=[{x:M,title:'路线 A  /  避免治理成本',range:'0.044 — 57.1',median:'中位 0.254',body:'概念不适用：烟花 PM2.5 弥散释放，\n无法通过捕集来避免治理成本。'},
 {x:6.87,title:'路线 B  /  健康损害',range:'0.0020 — 6.59',median:'中位 0.0225',body:'主导不确定性的是扩散参数 DK；\n它是唯一没有来源的参数。'}];
 tops.forEach(a=>{rect(s,a.x,1.91,5.8,2.13,C.soft);tx(s,a.title,a.x+.23,2.08,5.34,.36,19,{bold:true,color:C.purple});tx(s,a.range,a.x+.23,2.62,3.66,.51,29,{fontFace:'Arial',bold:true});tx(s,a.median,a.x+3.97,2.73,1.62,.3,14.3,{color:C.muted});tx(s,a.body,a.x+.23,3.27,5.34,.56,16.4,{color:C.muted});});
 tx(s,'临界扩散参数（范围 401—13,171）',M,4.49,5.8,.35,18,{bold:true,color:C.purple});
 num(s,'DK* = 1,901',M,4.99,5.8,.64,35);
 tx(s,'1,901 为中位数；53% 的参数组合在\n整个假定 DK 区间均显示“税低于损害”。',M,5.91,5.8,.72,17);
 tx(s,'绕开 DK：直接给观测浓度定价',6.87,4.49,5.8,.35,18,{bold:true,color:C.purple});
 num(s,'6—27 倍',6.87,4.99,5.8,.64,35);
 tx(s,'税负 / 健康损害的比值上界。\n不是点估计，也不是最优性结论。',6.87,5.91,5.8,.72,17);
}

// 13. Native chart with original contribution values and explicit units.
{
 const s=base(13,'稳健性检查','气象解释了一部分，但并非全部');
 tx(s,'区域天气并非初一特有',M,1.89,5.8,.45,23,{bold:true,color:C.purple});
 tx(s,'省级气象复现的分解贡献（百分点）',M,2.46,5.8,.32,15.5,{color:C.muted});
 s.addChart(pptx.ChartType.bar,[{name:'分解贡献',labels:['初一','除夕','前一天'],values:[11.9,11.8,9.7]}],{
  x:.62,y:2.95,w:5.89,h:2.45,barDir:'bar',showLegend:false,showTitle:false,
  chartColors:[C.purple],showValue:true,dataLabelPosition:'outEnd',dataLabelFormatCode:'0.0',
  dataLabelColor:C.purple,dataLabelBkgrdColor:C.white,dataLabelFormatCodeSourceLinked:false,dataLabelFontSize:18,
  catAxisLabelFontFace:'Microsoft YaHei',catAxisLabelFontSize:17,catAxisLabelColor:C.ink,
  valAxisMinVal:0,valAxisMaxVal:15,valAxisMajorUnit:5,valAxisLabelFontSize:12,valAxisLabelColor:C.muted,
  catGridLine:{style:'none'},valGridLine:{color:C.gray,size:.6},showBorder:false,showCatName:false,
  catAxisLineShow:false,valAxisLineShow:false,showShadow:false,showCatName:false,
  showMarker:false,gapSizePct:80,showValue:true
 });
 tx(s,'初一占省 × 年成分的 39%；\n控制省 × 年 NO2 后只剩 4.5 个点。',M,5.65,5.8,.72,17);
 rect(s,6.87,1.87,5.8,4.55,C.lilac);
 tx(s,'本地气象仅解释少量残差',7.13,2.08,5.27,.48,23,{bold:true,color:C.purple});
 num(s,'1.6',7.13,2.97,2,.8,47);tx(s,'个百分点（5%）',9.25,3.22,3.1,.38,20,{bold:true});
 tx(s,'本地气象对城市 × 年成分的解释量',7.13,3.98,5.27,.4,18);
 tx(s,'BLH 在代理变量之上仅增加 0.1 个百分点。',7.13,4.75,5.27,.72,17.5);
 tx(s,'城际离散仍高：p90 / p10 = 9.3',7.13,5.79,5.27,.36,18,{bold:true,color:C.purple});
 tx(s,'结论：区域气象并非春节特有机制；本地气象不足以解释城市层面的全部变异。',M,6.61,12,.31,16.4,{color:C.muted});
}

// 14. A dark conclusion page concentrates the policy takeaway.
{
 const s=base(14,'结论与政策','政策设计要跟上损害的时空尺度',true);
 const facts=[['测量','全国统一、按年的从价税，\n难以对准地区 × 年份的变异。'],['识别','因果识别失败是结构性的；\n不能据此判断“禁令无效”。'],['校准','无法给出点估计；\n能定位的是临界参数 DK*。']];
 facts.forEach((a,j)=>{const y=2.02+j*1.29;tx(s,a[0],M,y,1.08,.38,19,{color:'D9C1E7',bold:true});tx(s,a[1],2.02,y-.03,4.43,.92,19.5,{color:C.white});});
 rect(s,6.97,1.91,5.7,3.97,'4A315B');
 tx(s,'分层设定的政策含义',7.24,2.13,5.16,.41,22,{bold:true,color:C.white});
 tx(s,'省级：年度水平\n城市：时段与本地加价',7.24,2.88,5.16,1.0,23,{bold:true,color:C.white});
 tx(s,'从价改从量，仍不解决分辨率。\n市级工具也覆盖不到边界外传输。',7.24,4.37,5.16,.88,18,{color:'E4D9EA'});
 tx(s,'把禁令的成本与效果纳入核算。',M,6.36,12,.5,28,{bold:true,color:C.white});
}

// 15. Complete references from the existing revised deck, at a readable appendix scale.
{
 const s=base(15,'参考文献','主要参考文献');
 const cn=[
 '陆卜梵, 刘蓓蓓 (2022). 京津冀地区烟花爆竹禁放政策对空气质量的影响. 环境科学学报, 42(8), 26–35.',
 '胡丙鑫, 段菁春, 刘世杰, 等 (2019). 2018 年春节期间京津冀及周边地区烟花禁放效果评估. 环境科学研究, 32(2), 203–211.',
 '刘稳, 詹庆明, 戴文博, 等 (2022). 基于高频空间分析的襄阳市春节期间烟花爆竹禁放效果评估. 热带地理, 42(10), 1724–1738.',
 '安体富, 樊勇 (2006). 对我国消费税改革的评析与展望. 税务研究, (12), 35–37.',
 '庞凤喜, 王绿荫 (2020). 消费税改革的目标定位与路径选择. 税务研究, (1), 44–49.'
 ];
 const en=[
 'Chen, S., Jiang, L., Liu, W., & Song, H. (2022). Fireworks regulation, air pollution, and public health. RSUE, 92, 103722.',
 'Li, Y., Li, R., Wang, S., & Wei, W. (2025). Fireworks celebrations and air pollution. JEPM, 68(3), 640–660.',
 'Beiser-McGrath, L. F., Bernauer, T., & Prakash, A. (2023). Command and control or market-based instruments? Environmental Politics, 32(4), 586–618.',
 'Weitzman, M. L. (1974). Prices vs. quantities. Review of Economic Studies, 41(4), 477–491.',
 'Tang, A., Tang, A. Y. F., & Peng, P. Z. J. (2012). Recycling of global consumer fireworks. Journal of Pyrotechnics, 31, 22–32.'
 ];
 tx(s,'中文文献',M,1.9,5.7,.4,20,{bold:true,color:C.purple});
 tx(s,'英文文献',6.97,1.9,5.7,.4,20,{bold:true,color:C.purple});
 cn.forEach((v,i)=>tx(s,v,M,2.57+i*.83,5.69,.72,12.5,{valign:'top',breakLine:false}));
 en.forEach((v,i)=>tx(s,v,6.97,2.57+i*.83,5.69,.72,12.8,{fontFace:'Arial',valign:'top',breakLine:false}));
}

for(const b of bounds) {
 if(b.x<-.01 || b.y<-.01 || b.x+b.w>W+.01 || b.y+b.h>H+.01) throw new Error('Text box outside slide: '+JSON.stringify(b));
}
fs.writeFileSync(path.join(ROOT,'layout_manifest.json'),JSON.stringify(bounds,null,2));
pptx.writeFile({fileName:path.join(ROOT,'..','烟花爆竹管制-展示.pptx')});
