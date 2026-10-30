import {useEffect,useMemo,useState} from 'react';
import {ArrowLeft,ArrowRight,BookOpen,CalendarDays,Check,ChevronDown,ClipboardList,FileText,Gem,GraduationCap,Lightbulb,LoaderCircle,RefreshCw,Sparkles,Stars,Users,WandSparkles} from 'lucide-react';
import {createProject,DEMO_EVENTS,DEMO_OPTIONS,loadCatalog,makeDemoProject,type EventItem,type Options,type Project,type RequestData} from './api';
type Page='welcome'|'form'|'loading'|'result';
const star='✦';
function MagicStar({small=false}:{small?:boolean}){return <span aria-hidden="true" className={'magic-star '+(small?'small':'')}>{star}</span>}
function Loader({caption='Колдуем над вашим сценарием…'}:{caption?:string}){return <div className="magic-loading" role="status" aria-live="polite"><div className="loading-scene"><svg className="spell-art" viewBox="0 0 740 360" xmlns="http://www.w3.org/2000/svg" aria-label="Волшебная палочка выпускает изумрудные волны"><defs><linearGradient id="spellGold" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#ffdfa0"/><stop offset=".45" stopColor="#98702b"/><stop offset=".7" stopColor="#f8ce77"/><stop offset="1" stopColor="#4e3512"/></linearGradient><linearGradient id="spellEmerald" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#a5ffe0"/><stop offset=".35" stopColor="#00dbae"/><stop offset=".7" stopColor="#067d66"/><stop offset="1" stopColor="#6af6c8"/></linearGradient><filter id="spellGlow"><feGaussianBlur stdDeviation="5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs><g className="wand-svg"><path d="M64 296 L313 201 L327 202 L317 215 L68 312 Z" fill="url(#spellGold)" stroke="#6f4b1d" strokeWidth="3"/><path d="M64 296 L90 282 L105 293 L90 309 L68 312 Z" fill="#086e5a" stroke="#d9ae5e" strokeWidth="4"/><path d="M111 277 L135 266 L150 278 L128 292 Z M172 254 L192 245 L207 254 L187 269 Z" fill="#078d70" stroke="#d8b45f" strokeWidth="3"/><path d="M79 298 L311 208" stroke="#fff0bc" strokeWidth="2"/><circle cx="87" cy="296" r="8" fill="#05bd97" stroke="#f2d590" strokeWidth="3"/><circle cx="144" cy="278" r="5" fill="#05cfa3" stroke="#ffe5a3" strokeWidth="2"/></g><g className="magic-trails" fill="none" stroke="url(#spellEmerald)" strokeLinecap="round" filter="url(#spellGlow)"><path className="trail t1" d="M327 202 C375 123 439 91 510 136 S627 239 697 134" strokeWidth="12"/><path className="trail t2" d="M327 202 C380 163 412 272 524 222 S628 111 717 176" strokeWidth="8"/><path className="trail t3" d="M327 202 C359 111 415 34 516 71 S662 84 697 39" strokeWidth="5"/><path className="trail t4" d="M327 202 C426 230 414 296 525 294 S665 232 716 283" strokeWidth="5"/></g><g fill="#e8bc66"><text x="380" y="107" fontSize="28">✧</text><text x="574" y="176" fontSize="38">✦</text><text x="656" y="90" fontSize="23">✧</text><text x="478" y="301" fontSize="22">✦</text></g><circle className="spell-flash" cx="327" cy="202" r="20" fill="#7fffe1" filter="url(#spellGlow)"/></svg></div><h2><span className="selected-text-glint">Северус творит волшебство…</span></h2><p>{caption}</p><span className="loading-dots"><b/><b/><b/><b/><b/></span></div>}

function SideVines(){return <svg className="side-vines-svg" viewBox="0 0 96 920" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="vineGold" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#b8873e"/><stop offset=".5" stopColor="#ffe6a0"/><stop offset="1" stopColor="#b98039"/></linearGradient></defs><g fill="none" stroke="url(#vineGold)" strokeWidth="1.5" strokeLinecap="round"><path d="M26 8 C88 90 14 152 63 227 S20 365 60 450 S12 612 66 704 S20 845 44 920"/><path d="M27 85 Q6 55 10 38 M42 160 Q82 126 76 106 M49 247 Q10 214 11 181 M43 328 Q80 297 84 266 M55 408 Q16 376 10 350 M53 503 Q82 473 82 444 M43 594 Q12 566 12 533 M53 690 Q84 656 83 636 M49 789 Q11 757 12 725"/></g><g fill="url(#vineGold)" stroke="#9e752f" strokeWidth=".4"><path d="M10 38 Q-1 18 21 23 Q31 34 10 38 Z M76 106 Q61 92 63 77 Q86 78 76 106 Z M11 181 Q-2 160 21 159 Q33 172 11 181 Z M84 266 Q67 253 69 239 Q91 243 84 266 Z M10 350 Q-1 334 22 326 Q35 339 10 350 Z M82 444 Q64 431 71 415 Q94 419 82 444 Z M12 533 Q-2 510 19 505 Q33 516 12 533 Z M83 636 Q66 625 69 609 Q93 614 83 636 Z M12 725 Q-3 705 21 695 Q32 714 12 725 Z"/></g><g fill="#efc679" fontFamily="serif"><text x="70" y="58" fontSize="25">✧</text><text x="11" y="285" fontSize="19">✦</text><text x="63" y="384" fontSize="28">☾</text><text x="14" y="475" fontSize="22">✧</text><text x="67" y="568" fontSize="18">✦</text><text x="13" y="653" fontSize="24">☽</text><text x="60" y="835" fontSize="25">✧</text></g></svg>}
function Select({label,value,onChange,options}:{label:string;value:string;onChange:(s:string)=>void;options:{value:string;label:string}[]}){
 const [open,setOpen]=useState(false);
 const current=options.find(o=>o.value===value);
 return <div className="field custom-select-field"><span className="field-name">{label}</span><div className="glass-select" onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node))setOpen(false)}}>
  <button type="button" className="glass-select-trigger" aria-label={label} aria-haspopup="listbox" aria-expanded={open} onClick={()=>setOpen(v=>!v)} onKeyDown={e=>{if(e.key==='Escape')setOpen(false);if(e.key==='ArrowDown'&&!open){e.preventDefault();setOpen(true)}}}><span>{current?.label||'Выберите значение'}</span><ChevronDown size={16}/></button>
  {open&&<div className="glass-options" role="listbox" aria-label={label}>{options.map((option,i)=><button type="button" role="option" aria-selected={option.value===value} key={option.value} className={option.value===value?'chosen':''} onClick={()=>{onChange(option.value);setOpen(false)}} onKeyDown={e=>{if(e.key==='Escape'){setOpen(false);e.currentTarget.closest('.glass-select')?.querySelector<HTMLButtonElement>('.glass-select-trigger')?.focus()}if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const buttons=Array.from(e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('button')||[]);buttons[(i+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus()}}}>{option.label}</button>)}</div>}
 </div></div>
}
function NumberField({label,value,onChange,min,max}:{label:string;value:number;onChange:(n:number)=>void;min:number;max:number}){return <label className="field"><span>{label}</span><input type="number" value={value} min={min} max={max} onChange={e=>onChange(Number(e.target.value))}/></label>}
function App(){
 const [page,setPage]=useState<Page>('welcome');const [mode,setMode]=useState<'demo'|'api'>('demo');const [catalog,setCatalog]=useState<EventItem[]>(DEMO_EVENTS);const [options,setOptions]=useState<Options>(DEMO_OPTIONS);const [catalogError,setCatalogError]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [status,setStatus]=useState('queued');const [project,setProject]=useState<Project|null>(null);const [selectedVariant,setSelectedVariant]=useState(0);const [section,setSection]=useState<'timeline'|'materials'|'roles'>('timeline');
 const [form,setForm]=useState<RequestData>({event_id:'knowledge_day',region_id:'RU-SVE',grade:6,pupils_count:25,duration_minutes:45,format:'class_hour',participants:{teachers_count:1,parents_enabled:false,parents_count:0,parent_roles:[]},resources:{projector:true,printer:false,internet:true,audio:true,room:'classroom',available_materials:[]},teacher_preferences:{style:'interactive',script_detail:'detailed',difficulty:'standard',interaction_level:'medium',group_work:true,preparation_effort:'minimal',notes:null},generation:{variants_count:2,language:'ru'}});
 const patch=(value:Partial<RequestData>)=>setForm(old=>({...old,...value}));
 const selectedEvent=catalog.find(e=>e.id===form.event_id);const gradeGroup=form.grade<=4?'1-4':form.grade<=8?'5-8':'9-11';const allowedFormats=options.formats.filter(f=>!selectedEvent?.supported_formats?.length||selectedEvent.supported_formats.includes(f.value));const isAgeSupported=!selectedEvent?.supported_age_groups?.length||selectedEvent.supported_age_groups.includes(gradeGroup);
 useEffect(()=>{if(!allowedFormats.some(f=>f.value===form.format)&&allowedFormats.length){patch({format:allowedFormats[0].value})}},[form.event_id,catalog,options]);
 async function connect(){setBusy(true);setCatalogError('');try{const [events,opts]=await loadCatalog();setCatalog(events);setOptions(opts);setMode('api');setForm(old=>({...old,event_id:events.some(e=>e.id===old.event_id)?old.event_id:events[0]?.id||'',region_id:opts.regions[0]?.value||'RU-SVE'}))}catch(e){setCatalogError(e instanceof Error?e.message:'Ошибка подключения');setMode('demo')}finally{setBusy(false)}}
 function useDemo(){setMode('demo');setCatalog(DEMO_EVENTS);setOptions(DEMO_OPTIONS);setCatalogError('');setForm(old=>({...old,event_id:'knowledge_day',region_id:'RU-SVE',format:'class_hour'}))}
 const valid=form.event_id!==''&&form.pupils_count>=1&&form.pupils_count<=35&&form.grade>=1&&form.grade<=11&&isAgeSupported&&allowedFormats.some(x=>x.value===form.format)&&(!form.participants.parents_enabled||form.participants.parents_count>=1);
 async function generate(){setError('');if(!valid){setError('Проверьте параметры формы: возраст, количество участников или формат мероприятия.');return}setPage('loading');setStatus('queued');const loadingStartedAt=Date.now();try{let result:Project;if(mode==='demo'){await new Promise(r=>setTimeout(r,5600));result=makeDemoProject(form,catalog)}else result=await createProject(form,setStatus);await new Promise<void>(resolve=>setTimeout(resolve,Math.max(0,6800-(Date.now()-loadingStartedAt))));setProject(result);setSelectedVariant(0);setSection('timeline');setPage('result')}catch(e){setPage('form');setError(e instanceof Error?e.message:'Не удалось получить сценарий')}}
 const variant=project?.variants[selectedVariant];const mappedMaterials=useMemo(()=>new Map((variant?.materials||[]).map(m=>[m.material_id,m])),[variant]); 

 const [copied, setCopied] = useState(false);


async function copyScenario() {
  if (!variant) return;

  const lines: string[] = [];
  const add = (value = '') => lines.push(value);

  add(`СЦЕНАРИЙ: ${variant.title}`);
  add(`Мероприятие: ${selectedEvent?.title ?? form.event_id}`);
  add(`Класс: ${form.grade}`);
  add(`Продолжительность: ${form.duration_minutes} мин`);
  add('');

  if (variant.concept?.goal) {
    add(`Цель: ${variant.concept.goal}`);
    add('');
  }

  add('ЭТАПЫ МЕРОПРИЯТИЯ');

  (variant.timeline ?? []).forEach((block, index) => {
    add('');
    add(`${index + 1}. ${block.title}`);
    add(`Время: ${block.duration_minutes} мин`);

    if (block.purpose) {
      add(`Цель этапа: ${block.purpose}`);
    }

    if (block.teacher_script) {
      add(`Слова и действия педагога:\n${block.teacher_script}`);
    }

    if (block.pupil_actions?.length) {
      add('Действия учеников:');
      block.pupil_actions.forEach(action => add(`- ${action}`));
    }

    if (block.material_ids?.length) {
      const materials = block.material_ids
        .map(id => mappedMaterials.get(id)?.title)
        .filter(Boolean);

      if (materials.length) {
        add(`Материалы: ${materials.join(', ')}`);
      }
    }
  });

  if (variant.materials?.length) {
    add('');
    add('МАТЕРИАЛЫ');
    variant.materials.forEach(material => {
      add(`- ${material.title}`);
      if (material.content) add(material.content);
    });
  }

  if (variant.roles?.length) {
    add('');
    add('УЧАСТНИКИ И РОЛИ');
    variant.roles.forEach(role =>
      add(`- ${role.title}: ${role.count} чел.`)
    );
  }

  if (variant.teacher_instructions?.length) {
    add('');
    add('ПАМЯТКА ПЕДАГОГУ');
    variant.teacher_instructions.forEach(instruction =>
      add(`- ${instruction}`)
    );
  }

  try {
    await navigator.clipboard.writeText(lines.join('\n'));
    setCopied(true);
  } catch (err) {
    console.error('Ошибка копирования:', err);
    alert('Не удалось скопировать сценарий');
  }
}

 return <div className="app"><div className="side-ornament left"><SideVines/></div><div className="side-ornament right"><SideVines/></div>
 <div className="app-shell">{page!=='welcome'&&<div className="glass-doe-bg" aria-hidden="true"/>}<div className="page-jewel page-jewel-top" aria-hidden="true"><span className="gem-wing left"/><span className="gem-core"/><span className="gem-wing right"/></div><div className="page-jewel page-jewel-bottom" aria-hidden="true"><span className="gem-wing left"/><span className="gem-core"/><span className="gem-wing right"/></div>
 {page!=='welcome'&&<header className="topbar"><button className="brand" onClick={()=>setPage('welcome')} aria-label="На главную"><MagicStar small/><span>Северус</span></button><div className="topbar-mid"><MagicStar small/> <span className="selected-text-glint">Мастерская событий</span> <MagicStar small/></div><span className={'mode-badge '+(mode==='api'?'connected':'')}>{mode==='api'?'● API подключён':'◇ Демо-режим'}</span></header>}
 {page==='welcome'&&<main className="welcome"><div className="welcome-stars">✧ ✦ ✧</div><div className="welcome-overline">ВАША МАСТЕРСКАЯ ЧУДЕСНЫХ СОБЫТИЙ</div><div className="hero-logo-wrap"><img className="hero-logo" src="/assets/severus-logo.png" alt="Северус — магический логотип с календарём, волшебной палочкой и зелёной ланью"/></div><p className="welcome-subtitle">Пусть каждый школьный праздник станет маленькой историей,<br/> которую хочется помнить.</p><button className="primary hero-cta" onClick={()=>setPage('form')}><Sparkles size={18}/> Создать сценарий <ArrowRight size={18}/></button><div className="welcome-foot">ИДЕЯ <span>✧</span> ВОЛШЕБСТВО <span>✧</span> ВАШЕ СОБЫТИЕ</div></main>}
 {page==='form'&&<main className="page-content"><div className="heading"><span className="eyebrow"><MagicStar small/> <span className="selected-text-glint">КОНСТРУКТОР МЕРОПРИЯТИЯ</span></span><h1>Создадим немного <em>волшебства</em></h1><p>Расскажите о вашем событии — мы подготовим сценарий, наполненный идеями.</p></div>
 <div className="mode-switch"><div><b>Источник сценария</b><span>{mode==='demo'?'Учебный каталог (2 примера). Не совпадает с полным каталогом API; сервер не требуется.':'Сценарий создаётся существующим mock-бэкендом.'}</span></div><div className="mode-actions"><button className={mode==='demo'?'active':''} onClick={useDemo}>Демо</button><button className={mode==='api'?'active':''} onClick={connect} disabled={busy}>{busy?<LoaderCircle size={14} className="spin"/>:null} API</button></div></div>
 {catalogError&&<div className="notice error"><b>Сервер недоступен:</b> {catalogError}. Можно продолжить в демо-режиме.</div>}
 {error&&<div role="alert" className="notice error">{error.startsWith('Тестовая ошибка:') ? (
  <>
    <strong style={{ color: '#d93636', fontWeight: 700 }}>
      Тестовая ошибка:
    </strong>
    {error.slice('Тестовая ошибка:'.length)}
  </>
) : error}</div>}
 <div className="form-grid"><div className="form-main"><section className="panel"><div className="panel-heading"><span className="step-icon"><CalendarDays size={20}/></span><div><span className="step-label">ШАГ 01</span><h2>О событии</h2></div></div><div className="fields two"><Select label="Школьное мероприятие" value={form.event_id} onChange={v=>patch({event_id:v})} options={catalog.map(e=>({value:e.id,label:mode==='demo'?`${e.title} (учебный пример)`:e.title}))}/><Select label="Регион" value={form.region_id} onChange={v=>patch({region_id:v})} options={options.regions}/><Select label="Класс" value={String(form.grade)} onChange={v=>patch({grade:Number(v)})} options={options.grades.map(g=>({value:String(g),label:`${g} класс`}))}/><NumberField label="Количество учеников" value={form.pupils_count} min={1} max={35} onChange={v=>patch({pupils_count:v})}/><Select label="Формат мероприятия" value={form.format} onChange={v=>patch({format:v})} options={allowedFormats}/><Select label="Продолжительность" value={String(form.duration_minutes)} onChange={v=>patch({duration_minutes:Number(v)})} options={options.duration_minutes.map(o=>({value:String(o.value),label:o.label}))}/></div>{!isAgeSupported&&<div className="notice error">Выбранное мероприятие не поддерживает {form.grade} класс. Выберите другой класс или мероприятие.</div>}</section>
 <section className="panel"><div className="panel-heading"><span className="step-icon"><Users size={20}/></span><div><span className="step-label">ШАГ 02</span><h2>Участники и пространство</h2></div></div><div className="fields two"><NumberField label="Количество педагогов" value={form.participants.teachers_count} min={1} max={100} onChange={v=>patch({participants:{...form.participants,teachers_count:v}})}/><Select label="Помещение" value={form.resources.room} onChange={v=>patch({resources:{...form.resources,room:v}})} options={options.rooms}/></div><div className="toggles">{([['projector','Проектор'],['internet','Интернет'],['audio','Аудиосистема'],['printer','Принтер']] as const).map(([key,label])=><label className="check" key={key}><input type="checkbox" checked={form.resources[key]} onChange={e=>patch({resources:{...form.resources,[key]:e.target.checked}})}/><span className="check-icon"><Check size={12}/></span>{label}</label>)}</div><div className="form-divider"/><label className="check parent-check"><input type="checkbox" checked={form.participants.parents_enabled} onChange={e=>patch({participants:{...form.participants,parents_enabled:e.target.checked,parents_count:e.target.checked?1:0,parent_roles:e.target.checked?['audience']:[]}})}/><span className="check-icon"><Check size={12}/></span>В мероприятии участвуют родители</label>{form.participants.parents_enabled&&<div className="fields two extra"><NumberField label="Количество родителей" value={form.participants.parents_count} min={1} max={100} onChange={v=>patch({participants:{...form.participants,parents_count:v}})}/><fieldset className="parent-role-fieldset"><legend>Роли родителей (можно выбрать несколько)</legend>{([['audience','Зрители'],['helper','Помощники'],['active_participant','Активные участники'],['evaluator','Жюри / оценщики']] as const).map(([role,label])=><label className="check" key={role}><input type="checkbox" checked={form.participants.parent_roles.includes(role)} onChange={e=>patch({participants:{...form.participants,parent_roles:e.target.checked?[...form.participants.parent_roles,role]:form.participants.parent_roles.filter(r=>r!==role)}})}/><span className="check-icon"><Check size={12}/></span>{label}</label>)}</fieldset></div>}</section>
 <section className="panel"><div className="panel-heading"><span className="step-icon"><WandSparkles size={20}/></span><div><span className="step-label">ШАГ 03</span><h2>Ваши пожелания</h2></div></div><div className="fields two"><Select label="Стиль сценария" value={form.teacher_preferences.style} onChange={v=>patch({teacher_preferences:{...form.teacher_preferences,style:v}})} options={options.teacher_preferences.style||DEMO_OPTIONS.teacher_preferences.style}/><Select label="Детализация сценария" value={form.teacher_preferences.script_detail} onChange={v=>patch({teacher_preferences:{...form.teacher_preferences,script_detail:v}})} options={(options.teacher_preferences.script_detail||DEMO_OPTIONS.teacher_preferences.script_detail).map(option=>({...option,label:({brief:'Краткая',standard:'Стандартная',detailed:'Подробная'} as Record<string,string>)[option.value]||option.label}))}/></div><label className="field full"><span>Особые идеи и пожелания</span><textarea rows={3} placeholder="Например, добавить больше командных заданий…" value={form.teacher_preferences.notes||''} onChange={e=>patch({teacher_preferences:{...form.teacher_preferences,notes:e.target.value||null}})}/></label><div className="variant-choices"><div><b>Количество вариантов</b><span>Сколько сценариев подготовить?</span></div><div className="segment">{[1,2,3].map(n=><button key={n} type="button" className={form.generation.variants_count===n?'selected':''} onClick={()=>patch({generation:{...form.generation,variants_count:n}})}>{n}</button>)}</div></div></section></div>
 <aside className="form-aside"><div className="aside-card"><span className="aside-decoration">✦</span><div className="aside-calendar"><CalendarDays size={30}/></div><h3>Каждое событие —<br/><em>особенная история</em></h3><p>Магия начинается с одной идеи. Выберите параметры, а Северус подскажет, как воплотить её в жизнь.</p><div className="gold-rule"/><ul><li><Check size={15}/> Сценарий по вашим запросам</li><li><Check size={15}/> Пошаговый план мероприятия</li><li><Check size={15}/> Идеи и материалы для педагога</li></ul></div><div className="tip"><Lightbulb size={18}/><span>Для первого знакомства рекомендуем <b>демо-режим</b>. Он работает без подключения к серверу.</span></div></aside></div>
 <div className="form-bottom"><button className="secondary" onClick={()=>setPage('welcome')}><ArrowLeft size={16}/> На главную</button><button className="primary" disabled={!valid} onClick={generate}><WandSparkles size={19}/> Сотворить сценарий <ArrowRight size={18}/></button></div></main>}
 {page==='loading'&&<main className="loader-page"><Loader caption={mode==='demo'?'Волшебная палочка создаёт пробную историю…':status==='queued'?'Ожидаем начала генерации…':'Сервер создаёт сценарии вашего мероприятия…'}/></main>}
 {page==='result'&&variant&&<main className="page-content results"><div className="heading"><span className="eyebrow result-overline"><WandSparkles size={18}/> <span className="selected-text-glint">{project?.status==="partial"?"ГОТОВА ЧАСТЬ СЦЕНАРИЕВ":"ВАШ СЦЕНАРИЙ ГОТОВ"}</span></span><h1>История начинается <em>здесь</em></h1><p>{selectedEvent?.title||'Школьное мероприятие'} · {form.grade} класс · {form.duration_minutes} минут</p></div>{mode==='demo'&&<div className="notice demo-notice"><Sparkles size={16}/> Демо-результат: создан локально, не получен от бэкенда или LLM.</div>}{project?.status==="partial"&&<div role="status" className="notice error"><b>Сценарии готовы частично.</b> Не все варианты удалось сформировать. Ниже показаны только готовые сценарии.{!!project.variant_statuses?.length&&<ul>{project.variant_statuses.filter(v=>v.status!=="completed").map(v=><li key={v.variant_id}>Вариант {v.variant_id}: {v.status==="failed"?"не сформирован":v.status}</li>)}</ul>}{!!project.generation_issues?.length?<ul>{project.generation_issues.map((issue,i)=><li key={i}>{issue.variant_id?`Вариант ${issue.variant_id}: `:""}{issue.message||issue.code||"Причина не указана"}</li>)}</ul>:<p>Сервис не передал подробные причины отклонения вариантов.</p>}</div>}{!!project?.generation_warnings?.length&&<div role="status" className="notice generation-warnings"><b>Предупреждения сервера</b><ul>{project.generation_warnings.map((warning,i)=><li key={i}>{typeof warning==='string'?warning:warning.message||warning.code||'Предупреждение без описания'}</li>)}</ul></div>}<div className="results-header"><div><span className="step-label">ВАРИАНТЫ СЦЕНАРИЯ</span><div className="tabs">{project?.variants.map((v,i)=><button key={v.variant_id} onClick={()=>{setSelectedVariant(i);setSection('timeline')}} className={i===selectedVariant?'current':''}>Вариант {i+1}</button>)}</div></div><button className="primary new-scenario" onClick={()=>setPage('form')}><RefreshCw size={15}/> Новый сценарий</button></div>
 <section className="panel result-hero"><div className="result-hero-star">✧</div><span className="step-label">{variant.variant_id.toUpperCase()} · ГОТОВЫЙ СЦЕНАРИЙ</span><h2>{variant.title}</h2><p>{variant.concept?.summary}</p><div className="concept-goal"><Gem size={17}/><span><b>Цель:</b> {variant.concept?.goal}</span></div></section>
 <div className="result-layout"><div className="panel result-main"><div className="result-tabs"><button className={section==='timeline'?'current':''} onClick={()=>setSection('timeline')}><ClipboardList size={17}/> Этапы</button><button className={section==='materials'?'current':''} onClick={()=>setSection('materials')}><BookOpen size={17}/> Материалы</button><button className={section==='roles'?'current':''} onClick={()=>setSection('roles')}><Users size={17}/> Участники</button></div>
 {section==='timeline'&&<div className="timeline">{variant.timeline?.map((block,i)=><article className="timeline-step" key={block.block_id}><span className="timeline-index">{String(i+1).padStart(2,'0')}</span><div className="timeline-body"><div className="timeline-top"><h3>{block.title}</h3><span>{block.start_minute}–{block.start_minute+block.duration_minutes} мин</span></div>{block.purpose&&<p className="purpose">{block.purpose}</p>}{block.teacher_script&&<div className="teacher-script"><b>Слова и действия педагога</b><p>{block.teacher_script}</p></div>}{!!block.pupil_actions?.length&&<div className="pupil-actions"><b>Что делают ученики</b><ul>{block.pupil_actions.map((a,j)=><li key={j}>{a}</li>)}</ul></div>}{!!block.material_ids?.length&&<div className="material-links">{block.material_ids.map(id=>mappedMaterials.get(id)).filter(Boolean).map(m=><span key={m!.material_id}><FileText size={13}/>{m!.title}</span>)}</div>}</div></article>)}</div>}
 {section==='materials'&&<div className="material-grid">{!variant.materials?.length?<p>Дополнительные материалы не требуются.</p>:variant.materials.map(m=><article className="material-card" key={m.material_id}><FileText size={22}/><h3>{m.title}</h3><p>{m.content||'Материал к сценарию'}</p></article>)}</div>}
 {section==='roles'&&<div className="role-list">{variant.roles?.map(r=><div key={r.role_id}><Users size={19}/><b>{r.title}</b><span>{r.count} чел.</span></div>)}</div>}</div><aside className="result-aside"><div className="panel summary"><h3><Stars size={18}/> Ожидаемые результаты</h3><ul>{variant.concept?.expected_outcomes?.map((x,i)=><li key={i}><Check size={14}/>{x}</li>)}</ul></div><div className="panel summary"><h3><GraduationCap size={19}/> Памятка педагогу</h3><ul>{variant.teacher_instructions?.map((x,i)=><li key={i}><Check size={14}/>{x}</li>)}</ul></div>{!!variant.quality_report?.issues?.length&&<div className="notice warning"><b>Обратите внимание</b>{variant.quality_report.issues.map((issue,i)=><p key={i}>{issue.message}</p>)}</div>}<button className="secondary copy" onClick={copyScenario}><ClipboardList size={15}/> {copied ? 'Скопировано!' : 'Копировать план'}</button></aside></div></main>}
 <footer className="footer"><span>✦</span> Северус · Волшебство школьных событий <span>✦</span></footer></div></div>
}
export default App;
