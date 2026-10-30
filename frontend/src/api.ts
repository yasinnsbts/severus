export type Choice={value:string;label:string};
export type EventItem={id:string;title:string;category:string;supported_age_groups:string[];supported_formats:string[]};
export type Options={regions:Choice[];grades:number[];duration_minutes:{value:number;label:string}[];formats:Choice[];rooms:Choice[];teacher_preferences:Record<string,Choice[]>};
export type RequestData={event_id:string;region_id:string;grade:number;pupils_count:number;duration_minutes:number;format:string;participants:{teachers_count:number;parents_enabled:boolean;parents_count:number;parent_roles:string[]};resources:{projector:boolean;printer:boolean;internet:boolean;audio:boolean;room:string;available_materials:string[]};teacher_preferences:{style:string;script_detail:string;difficulty:string;interaction_level:string;group_work:boolean;preparation_effort:string;notes:string|null};generation:{variants_count:number;language:'ru'}};
export type TimelineBlock={block_id:string;start_minute:number;duration_minutes:number;title:string;purpose?:string;teacher_script?:string;pupil_actions?:string[];material_ids?:string[]};
export type Variant={variant_id:string;title:string;concept?:{summary?:string;goal?:string;tasks?:string[];expected_outcomes?:string[]};roles?:{role_id:string;title:string;count:number}[];timeline?:TimelineBlock[];materials?:{material_id:string;title:string;type?:string;content?:string;used_in_blocks?:string[]}[];teacher_instructions?:string[];quality_report?:{status:string;issues?:{code:string;severity:string;message:string}[]}};
export type GenerationIssue={code?:string;message?:string;field?:string;variant_id?:string};
export type GenerationWarning=string|{code?:string;message?:string;field?:string};
export type Project={schema_version:string;project_id:string;status:string;variants:Variant[];generation_issues?:GenerationIssue[];generation_warnings?:GenerationWarning[];variant_statuses?:{variant_id:string;status:string}[]};
const apiBase=(import.meta.env.VITE_API_BASE_URL||'http://127.0.0.1:8000').replace(/\/$/,'');
async function getJson<T>(path:string,init?:RequestInit):Promise<T>{
 const url=path.startsWith('http')?path:`${apiBase}${path}`;
 let r:Response;try{r=await fetch(url,{...init,headers:{'Content-Type':'application/json',...init?.headers}})}catch{throw new Error('Нет соединения с сервером. Проверьте, что бэкенд запущен на '+apiBase)}
 const data=await r.json().catch(()=>({}));
 if(!r.ok){const err=data?.error||data?.detail;let message=typeof err==='string'?err:err?.message||`Ошибка сервера (${r.status})`;if(Array.isArray(err))message=err.map((x:{msg?:string})=>x.msg||'Ошибка проверки').join('; ');throw new Error(message)}
 return data as T;
}
export async function loadCatalog(){return Promise.all([getJson<EventItem[]>('/api/v1/catalog/events'),getJson<Options>('/api/v1/catalog/options')]);}
export async function createProject(request:RequestData,onStatus:(status:string)=>void):Promise<Project>{
 const started=await getJson<{job_id:string;project_id:string;status_url:string;project_url:string}>('/api/v1/generations',{method:'POST',body:JSON.stringify(request)});
 const statusUrl=started.status_url||`/api/v1/generations/${started.job_id}`;
 const projectUrl=started.project_url||`/api/v1/projects/${started.project_id}`;

 for(let i=0;i<90;i++){
  const state=await getJson<{
   status:string;
   completed_variants?:number;
   errors?:GenerationIssue[];
   warnings?:GenerationWarning[];
   variants?:{variant_id:string;status:string}[];
  }>(statusUrl);

  onStatus(state.status);

  if(state.status==='completed'||(state.status==='partial'&&(state.completed_variants??0)>0)){
   const result=await getJson<Project>(projectUrl);
   // Metadata belongs to the job status, not necessarily the project payload.
   return {...result, generation_issues:state.errors||[], generation_warnings:state.warnings||[],
    variant_statuses:state.variants||[], status:state.status};
  }

  if(state.status==='failed'||state.status==='partial'){
   const reasons=(state.errors||[])
    .map(error=>error.message||error.code)
    .filter(Boolean);

   throw new Error(
    reasons.length
     ? reasons.join('; ')
     : `Генерация не завершена (${state.status}). Сервис не передал подробную причину. Задание: ${started.job_id}`
   );
  }

  await new Promise(resolve=>setTimeout(resolve,1200));
 }

 throw new Error('Превышено время ожидания генерации');
}

export const DEMO_EVENTS:EventItem[]=[{id:'knowledge_day',title:'День знаний',category:'Праздники',supported_age_groups:['1-4','5-8','9-11'],supported_formats:['class_hour','school_event','interactive_lesson']},{id:'teacher_day',title:'День учителя',category:'Школьные праздники',supported_age_groups:['1-4','5-8','9-11'],supported_formats:['class_hour','school_event']}];
export const DEMO_OPTIONS:Options={regions:[{value:'RU-SVE',label:'Свердловская область'}],grades:Array.from({length:11},(_,i)=>i+1),duration_minutes:[30,45,60,90].map(v=>({value:v,label:`${v} минут`})),formats:[{value:'class_hour',label:'Классный час'},{value:'school_event',label:'Общешкольное мероприятие'},{value:'interactive_lesson',label:'Интерактивное занятие'}],rooms:[{value:'classroom',label:'Класс'},{value:'assembly_hall',label:'Актовый зал'},{value:'gym',label:'Спортзал'},{value:'other',label:'Другое'}],teacher_preferences:{style:[{value:'classic',label:'Классический'},{value:'interactive',label:'Интерактивный'},{value:'creative',label:'Творческий'},{value:'research',label:'Исследовательский'}],script_detail:[{value:'brief',label:'Краткая'},{value:'standard',label:'Стандартная'},{value:'detailed',label:'Подробная'}]}};
export function makeDemoProject(input:RequestData,events:EventItem[]):Project{
 const event=events.find(e=>e.id===input.event_id)?.title||'Школьное мероприятие';
 const motifs=[['Тайна маленьких открытий','Вдохновить учеников на совместные открытия','Командная игра и поиск необычных решений'],['Созвездие идей','Развить творческое мышление и взаимопомощь','Мастерская идей и творческое задание'],['Путь к успеху','Сформировать мотивацию и чувство команды','Квиз и обсуждение планов']];
 return {schema_version:'demo',project_id:'demo-local',status:'completed',variants:Array.from({length:input.generation.variants_count},(_,i)=>{const [name,goal,activity]=motifs[i];const middle=input.duration_minutes-10;return {variant_id:`v${i+1}`,title:`${event} — ${name} (демо)`,concept:{summary:`Пробный сценарий «${name}» для ${input.grade} класса.`,goal,tasks:[activity],expected_outcomes:['Дети смогут поделиться впечатлениями и работать в команде.']},roles:[{role_id:'teacher',title:'Педагог',count:input.participants.teachers_count},{role_id:'students',title:'Ученики',count:input.pupils_count}],timeline:[{block_id:'block_01',start_minute:0,duration_minutes:5,title:'Волшебное приветствие',purpose:'Настроить участников на совместную работу',teacher_script:'Приветствуйте учеников. Предложите каждому назвать одно слово, которое ассоциируется с новым учебным годом.',pupil_actions:['Представляются и делятся ожиданиями.'],material_ids:[]},{block_id:'block_02',start_minute:5,duration_minutes:middle,title:activity,purpose:goal,teacher_script:'Разделите класс на небольшие группы. Объясните задание, распределите материалы и помогайте участникам.',pupil_actions:['Обсуждают идеи','Совместно представляют результат'],material_ids:['m1']},{block_id:'block_03',start_minute:5+middle,duration_minutes:5,title:'Финальное созвездие',purpose:'Закрепить впечатления',teacher_script:'Предложите каждому участнику поделиться самым интересным открытием сегодняшнего дня.',pupil_actions:['Подводят итоги и обмениваются впечатлениями.'],material_ids:[]}],materials:[{material_id:'m1',type:'handout',title:'Карточки творческого задания',content:'Подготовьте бумагу и цветные карандаши для каждой команды.',used_in_blocks:['block_02']}],teacher_instructions:['Заранее подготовьте необходимые материалы.','При необходимости адаптируйте задания к возрасту участников.'],quality_report:{status:'warning',issues:[{code:'DEMO',severity:'warning',message:'Это демонстрационный сценарий. Он создан локально и не является ответом сервера или LLM.'}]}};})};
}
