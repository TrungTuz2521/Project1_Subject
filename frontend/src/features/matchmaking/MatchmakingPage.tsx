import { useEffect, useState } from 'react';
import { matchPostsService } from '../../services/matchPosts';
import { proposalsService } from '../../services/proposals';
import { matchesService } from '../../services/matches';
import { notificationsService } from '../../services/notifications';
import { teamsService } from '../../services/teams';
import { errorMessage } from '../../services/api';
import type { Match, Notification, PostSummary, Proposal, Team } from '../../types/api';

type Tab = 'posts' | 'teams' | 'proposals' | 'matches' | 'notifications';
const tabs: {id:Tab;label:string}[]=[{id:'posts',label:'Bảng tin'},{id:'teams',label:'Đội bóng'},{id:'proposals',label:'Đề xuất ghép'},{id:'matches',label:'Trận đấu'},{id:'notifications',label:'Thông báo'}];
const postNames={FIND_OPPONENT:'Tìm đối thủ',RECRUIT_MEMBERS:'Tuyển thành viên',LOOK_FOR_TEAM:'Tìm đội',RANDOM_SQUAD:'Ghép đội ngẫu nhiên'};
const statusLabel:Record<string,string>={OPEN:'Đang mở',LOCKED:'Đã khóa',MATCHED:'Đã ghép',EXPIRED:'Hết hạn',CANCELLED:'Đã hủy',PENDING_DEPOSIT:'Chờ đặt cọc',PENDING_CONFIRMATION:'Chờ xác nhận',ACCEPTED:'Đã đồng ý',REJECTED:'Đã từ chối',EXPIRED_PROPOSAL:'Hết hạn',SUGGESTED:'Đề xuất',CONFIRMED:'Đã xác nhận',COMPLETED:'Đã hoàn thành',CANCELLED_MATCH:'Đã hủy'};
const date=(value:string|null|undefined)=>value?new Date(value).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'Chưa xác định';
export function MatchmakingPage(){
 const [tab,setTab]=useState<Tab>('posts'); const [posts,setPosts]=useState<PostSummary[]>([]); const [teams,setTeams]=useState<Team[]>([]);
 const [proposals,setProposals]=useState<Proposal[]>([]); const [matches,setMatches]=useState<Match[]>([]); const [notifications,setNotifications]=useState<Notification[]>([]);
 const [loading,setLoading]=useState(false); const [error,setError]=useState(''); const [busy,setBusy]=useState<number|null>(null); const [notice,setNotice]=useState('');
 const [filter,setFilter]=useState('ALL'); const [search,setSearch]=useState('');
 async function load(){
  setLoading(true);setError('');
  try{
   const [p,t,pr,m,n]=await Promise.all([matchPostsService.list(),teamsService.list(),proposalsService.list(),matchesService.list(),notificationsService.list()]);
   setPosts(p.data);setTeams(t.data);setProposals(pr.data);setMatches(m.data);setNotifications(n.data);
  }catch(e){setError(errorMessage(e));}finally{setLoading(false);}
 }
 useEffect(()=>{void load();},[]);
 const visiblePosts=posts.filter(p=>(filter==='ALL'||p.post_type===filter)&&(p.title.toLocaleLowerCase().includes(search.toLocaleLowerCase())));
 async function respond(id:number,decision:'ACCEPTED'|'DECLINED'){
  if(!window.confirm(decision==='ACCEPTED'?'Bạn xác nhận đồng ý đề xuất này?':'Bạn chắc chắn muốn từ chối đề xuất này?'))return;
  setBusy(id);setNotice('');
  try{await proposalsService.respond(id,decision);setNotice('Đã gửi phản hồi. Trạng thái trận chỉ được xác nhận khi Backend hoàn tất Booking.');await load();}
  catch(e){setError(errorMessage(e));}finally{setBusy(null);}
 }
 async function readNotification(id:number){
  setBusy(id);try{await notificationsService.markRead(id);setNotifications(old=>old.map(n=>n.notification_id===id?{...n,is_read:true}:n));}
  catch(e){setError(errorMessage(e));}finally{setBusy(null);}
 }
 return <section className="mm-page">
  <div className="account-eyebrow">KẾT NỐI TỪ SÂN CỎ</div>
  <div className="account-page-heading"><div><h1>Ghép đội & tìm trận<span>.</span></h1><p>Tìm đồng đội, khám phá bài đăng và theo dõi các đề xuất ghép trận.</p></div><button className="account-secondary-button" onClick={()=>void load()} disabled={loading}>↻ Làm mới</button></div>
  <div className="mm-tabs" role="tablist">{tabs.map(t=><button key={t.id} role="tab" aria-selected={tab===t.id} className={tab===t.id?'active':''} onClick={()=>setTab(t.id)}>{t.label}</button>)}</div>
  {notice&&<div className="notice-success" role="status">{notice}</div>}
  {error&&<div className="notice-error" role="alert">{error}<button onClick={()=>setError('')}>Đóng</button></div>}
  {loading?<div className="account-panel account-loading"><span className="spinner"/> Đang tải dữ liệu…</div>:<>
   {tab==='posts'&&<><div className="mm-toolbar"><input aria-label="Tìm bài đăng" placeholder="Tìm bài đăng…" value={search} onChange={e=>setSearch(e.target.value)}/><select aria-label="Lọc loại bài" value={filter} onChange={e=>setFilter(e.target.value)}><option value="ALL">Tất cả loại bài</option>{Object.entries(postNames).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
    {visiblePosts.length===0?<Empty text="Chưa có bài đăng phù hợp."/>:<div className="mm-grid">{visiblePosts.map(p=><article className="mm-card" key={p.post_id}><div className="mm-card-top"><span className="mm-type">{postNames[p.post_type]}</span><span className="mm-status">{statusLabel[p.status]??p.status}</span></div><h3>{p.title}</h3><p>Trình độ: {p.skill_level} · Sân: {p.pitch_type??'Chưa chọn'}</p><p>Thời gian: {date(p.match_time)}</p><p>Người tham gia: {p.current_players}{p.required_players?'/'+p.required_players:''}</p><small>Hết hạn: {date(p.expiry_time)}</small></article>)}</div>}</>}
   {tab==='teams'&&(teams.length?<div className="mm-grid">{teams.map(t=><article className="mm-card" key={t.team_id}><span className="mm-type">{t.creation_type==='AI_RANDOM'?'Đội ghép tự động':'Đội của bạn'}</span><h3>{t.team_name}</h3><p>{t.active_member_count} thành viên</p><span className="mm-status">{t.status==='ACTIVE'?'Đang hoạt động':'Ngừng hoạt động'}</span></article>)}</div>:<Empty text="Bạn chưa có đội bóng nào."/>)}
   {tab==='proposals'&&(proposals.length?<div className="mm-grid">{proposals.map(p=><article className="mm-card" key={p.proposal_id}><div className="mm-card-top"><span className="mm-type">{p.proposal_type==='OPPONENT'?'Ghép đối thủ':'Tuyển thành viên'}</span><span className="mm-status">{statusLabel[p.status]??p.status}</span></div><h3>Đề xuất #{p.proposal_id}</h3><p>Mức độ phù hợp: {p.compatibility_score}%</p><p>Hết hạn: {date(p.expires_at)}</p><div className="mm-actions">{p.status==='PENDING_CONFIRMATION'?<><button disabled={busy===p.proposal_id} onClick={()=>void respond(p.proposal_id,'ACCEPTED')}>Đồng ý</button><button className="secondary" disabled={busy===p.proposal_id} onClick={()=>void respond(p.proposal_id,'DECLINED')}>Từ chối</button></>:<small>Không cần phản hồi</small>}</div></article>)}</div>:<Empty text="Chưa có đề xuất ghép trận." />)}
   {tab==='matches'&&(matches.length?<div className="mm-grid">{matches.map(m=><article className="mm-card" key={m.match_id}><span className="mm-type">Trận #{m.match_id}</span><h3>{m.status==='CONFIRMED'?'Trận đã xác nhận':m.status==='SUGGESTED'?'Đang chờ xác nhận':'Trạng thái trận đấu'}</h3><p>Thời gian: {date(m.match_time)}</p><span className="mm-status">{statusLabel[m.status]??m.status}</span></article>)}</div>:<Empty text="Chưa có trận đấu nào." />)}
   {tab==='notifications'&&(notifications.length?<div className="mm-list">{notifications.map(n=><article className={n.is_read?'mm-notice':'mm-notice unread'} key={n.notification_id}><div><strong>{n.title}</strong><p>{n.content}</p><small>{date(n.created_at)} · {n.notification_type}</small></div>{!n.is_read&&<button disabled={busy===n.notification_id} onClick={()=>void readNotification(n.notification_id)}>Đánh dấu đã đọc</button>}</article>)}</div>:<Empty text="Bạn chưa có thông báo." />)}
  </>}
  <div className="mm-footnote">Lịch thi đấu chính thức chỉ gồm trận CONFIRMED. Trận SUGGESTED chưa được xem là đã đặt sân; frontend không tự tạo booking hoặc xác nhận thanh toán.</div>
 </section>;
}
function Empty({text}:{text:string}){return <div className="account-panel mm-empty"><span>◎</span><h3>{text}</h3><p>Khi có dữ liệu từ hệ thống, nội dung sẽ xuất hiện tại đây.</p></div>}
