import { useEffect, useMemo, useState } from 'react';
import { matchesService } from '../../services/matches';
import { errorMessage } from '../../services/api';
import type { Match, MatchDetail } from '../../types/api';

type CalendarView='day'|'week'|'month';
const ymd=(date:Date)=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
const label=(value:string)=>new Date(value).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'full',timeStyle:'short'});
function startOfWeek(value:Date){const date=new Date(value);const weekday=(date.getDay()+6)%7;date.setDate(date.getDate()-weekday);date.setHours(0,0,0,0);return date;}
export function SchedulePage(){
 const [matches,setMatches]=useState<Match[]>([]);const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [view,setView]=useState<CalendarView>('week');
 const [selected,setSelected]=useState(ymd(new Date()));const [detail,setDetail]=useState<MatchDetail|null>(null);const [detailError,setDetailError]=useState('');
 useEffect(()=>{const controller=new AbortController();setLoading(true);matchesService.list(1,undefined,controller.signal).then(r=>setMatches(r.data)).catch(e=>{if(!controller.signal.aborted)setError(errorMessage(e));}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();},[]);
 const selectedDate=new Date(selected+'T12:00:00+07:00');
 const visible=useMemo(()=>matches.filter(match=>{
  const day=ymd(new Date(match.match_time));if(view==='day')return day===selected;
  if(view==='month')return day.slice(0,7)===selected.slice(0,7);
  const start=startOfWeek(selectedDate);const end=new Date(start);end.setDate(start.getDate()+7);const time=new Date(match.match_time).getTime();return time>=start.getTime()&&time<end.getTime();
 }).sort((a,b)=>Date.parse(a.match_time)-Date.parse(b.match_time)),[matches,view,selected]);
 const confirmed=visible.filter(m=>m.status==='CONFIRMED');const suggested=visible.filter(m=>m.status==='SUGGESTED');
 function shift(delta:number){const d=new Date(selectedDate);if(view==='day')d.setDate(d.getDate()+delta);else if(view==='week')d.setDate(d.getDate()+delta*7);else d.setMonth(d.getMonth()+delta);setSelected(ymd(d));}
 async function openMatch(id:number){setDetail(null);setDetailError('');try{const result=await matchesService.get(id);setDetail(result.data);}catch(e){setDetailError(errorMessage(e));}}
 return <section className="mm-page"><div className="account-eyebrow">LỊCH THI ĐẤU</div><div className="account-page-heading"><div><h1>Lịch thi đấu<span>.</span></h1><p>Chỉ trận đã CONFIRMED được tính là lịch chính thức. Trận SUGGESTED được hiển thị riêng.</p></div><button className="account-secondary-button" onClick={()=>window.location.hash='/matchmaking'}>Quản lý ghép trận</button></div>
  <section className="account-panel"><div className="schedule-toolbar"><div className="schedule-switch">{(['day','week','month'] as CalendarView[]).map(v=><button className={view===v?'active':''} key={v} onClick={()=>setView(v)}>{v==='day'?'Ngày':v==='week'?'Tuần':'Tháng'}</button>)}</div><div className="schedule-date-nav"><button onClick={()=>shift(-1)} aria-label="Khoảng trước">←</button><input type="date" value={selected} onChange={e=>setSelected(e.target.value)}/><button onClick={()=>shift(1)} aria-label="Khoảng sau">→</button><button className="account-secondary-button" onClick={()=>setSelected(ymd(new Date()))}>Hôm nay</button></div></div>
  {loading?<div className="account-loading">Đang tải lịch thi đấu…</div>:error?<div className="notice-error">{error}</div>:<>
   <div className="schedule-summary"><span><b>{confirmed.length}</b> trận đã xác nhận</span><span><b>{suggested.length}</b> đề xuất chưa xác nhận</span><span><b>{view==='month'?selected.slice(0,7):view==='week'?'Tuần bắt đầu '+ymd(startOfWeek(selectedDate)):selected}</b></span></div>
   {confirmed.length===0&&suggested.length===0?<div className="mm-empty"><h3>Không có trận trong khoảng thời gian này</h3><p>Các trận được tạo sau khi ghép đội sẽ xuất hiện tại đây.</p></div>:<div className="schedule-groups">
    {confirmed.length>0&&<section><h3>Trận đã xác nhận</h3>{confirmed.map(m=><button className="schedule-match confirmed" key={m.match_id} onClick={()=>void openMatch(m.match_id)}><span className="schedule-date">{label(m.match_time)}</span><strong>Trận #{m.match_id}</strong><span className="mm-status">Đã xác nhận</span></button>)}</section>}
    {suggested.length>0&&<section><h3>Đang chờ booking / cọc</h3>{suggested.map(m=><button className="schedule-match suggested" key={m.match_id} onClick={()=>void openMatch(m.match_id)}><span className="schedule-date">{label(m.match_time)}</span><strong>Đề xuất trận #{m.match_id}</strong><span className="mm-status">Chưa phải lịch chính thức</span></button>)}</section>}
   </div>}
  </>}</section>
  {detailError&&<div className="notice-error">{detailError}</div>}{detail&&<section className="account-panel schedule-detail"><div className="account-section-heading"><div><span className="mm-type">CHI TIẾT TRẬN ĐẤU</span><h2>Trận #{detail.match_id}</h2></div><button className="account-secondary-button" onClick={()=>setDetail(null)}>Đóng</button></div><p><b>Thời gian:</b> {label(detail.match_time)} – {label(detail.end_time)}</p><p><b>Trạng thái:</b> {detail.status==='CONFIRMED'?'Đã xác nhận':detail.status==='SUGGESTED'?'Đề xuất, chờ booking và cọc':detail.status}</p><p><b>Sân:</b> {detail.booking?'Sân #'+detail.booking.pitch_id:'Backend chưa cung cấp booking hoàn tất'}</p><div className="schedule-team-list">{detail.teams.map(team=><span key={team.team_id}>{team.team_name}</span>)}</div></section>}
 </section>;
}
