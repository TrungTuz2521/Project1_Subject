import { useCallback, useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { matchPostsService } from '../../services/matchPosts';
import { proposalsService } from '../../services/proposals';
import { matchesService } from '../../services/matches';
import { notificationsService } from '../../services/notifications';
import { teamsService } from '../../services/teams';
import { errorMessage } from '../../services/api';
import { session } from '../../stores/session';
import type { Match, MatchDetail, MatchPost, Notification, PostCreate, PostSummary, PostType, Proposal, ProposalDetail, Team, PitchType, SkillLevel, TeamPaymentRule } from '../../types/api';

type Tab='posts'|'teams'|'proposals'|'matches'|'notifications';
const tabs:{id:Tab;label:string}[]=[{id:'posts',label:'Bảng tin bài đăng'},{id:'teams',label:'Đội bóng'},{id:'proposals',label:'Đề xuất ghép'},{id:'matches',label:'Trận đấu'},{id:'notifications',label:'Thông báo'}];
const postNames:Record<PostType,string>={FIND_OPPONENT:'Tìm đối thủ',RECRUIT_MEMBERS:'Tuyển thành viên',LOOK_FOR_TEAM:'Tìm đội',RANDOM_SQUAD:'Ghép đội ngẫu nhiên'};
const postStatuses:Record<string,string>={OPEN:'Đang mở',LOCKED:'Đang ghép',MATCHED:'Đã ghép',EXPIRED:'Hết hạn',CANCELLED:'Đã hủy',PENDING_DEPOSIT:'Chờ cọc'};
const statusNames:Record<string,string>={PENDING_CONFIRMATION:'Chờ xác nhận',ACCEPTED:'Hai bên đã đồng ý',REJECTED:'Đã từ chối',EXPIRED:'Hết hạn',SUGGESTED:'Chờ booking/cọc',CONFIRMED:'Đã xác nhận',COMPLETED:'Hoàn thành',CANCELLED:'Đã hủy'};
const skillNames:Record<SkillLevel,string>={BEGINNER:'Mới chơi',AMATEUR:'Phong trào',INTERMEDIATE:'Trung bình',SEMI_PRO:'Bán chuyên',PRO:'Chuyên nghiệp'};
const pitchNames:Record<PitchType,string>={PITCH_5:'Sân 5',PITCH_7:'Sân 7',PITCH_11:'Sân 11'};
const dateLabel=(v:string|null|undefined)=>v?new Date(v).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'Chưa xác định';
function localInput(date:Date){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(date);
 const val=(k:string)=>parts.find(p=>p.type===k)?.value??'00';
 return val('year')+'-'+val('month')+'-'+val('day')+'T'+val('hour')+':'+val('minute');
}
function asOffset(value:string){return value?value+':00+07:00':undefined;}
function initialForm(){const start=new Date(Date.now()+24*3600000);const end=new Date(start.getTime()+90*60000);return {type:'FIND_OPPONENT' as PostType,title:'',description:'',teamId:'',pitchType:'PITCH_7' as PitchType,skill:'INTERMEDIATE' as SkillLevel,matchTime:localInput(start),endTime:localInput(end),expiryTime:localInput(new Date(start.getTime()-2*3600000)),paymentRule:'SPLIT_EQUAL' as TeamPaymentRule,requiredPlayers:'1'};}
export function MatchmakingPage({initialTab='posts'}:{initialTab?:Tab}){
 const current=session.getSnapshot();const [tab,setTab]=useState<Tab>(initialTab);
 const [posts,setPosts]=useState<PostSummary[]>([]);const [myPosts,setMyPosts]=useState<MatchPost[]>([]);const [teams,setTeams]=useState<Team[]>([]);
 const [proposals,setProposals]=useState<Proposal[]>([]);const [matches,setMatches]=useState<Match[]>([]);const [notifications,setNotifications]=useState<Notification[]>([]);
 const [loading,setLoading]=useState(false);const [errors,setErrors]=useState<string[]>([]);const [busy,setBusy]=useState<number|null>(null);const [notice,setNotice]=useState('');
 const [search,setSearch]=useState('');const [postFilter,setPostFilter]=useState('ALL');const [pitchFilter,setPitchFilter]=useState('ALL');const [skillFilter,setSkillFilter]=useState('ALL');
 const [mineOnly,setMineOnly]=useState(false);const [fromDate,setFromDate]=useState('');const [toDate,setToDate]=useState('');const [showCreate,setShowCreate]=useState(false);const [form,setForm]=useState(initialForm);
 const [postDetail,setPostDetail]=useState<MatchPost|null>(null);const [proposalDetail,setProposalDetail]=useState<ProposalDetail|null>(null);const [matchDetail,setMatchDetail]=useState<MatchDetail|null>(null);
 const [editingPost,setEditingPost]=useState(false);const [editTitle,setEditTitle]=useState('');const [editDescription,setEditDescription]=useState('');
 const [detailError,setDetailError]=useState('');
 const load=useCallback(async()=>{
  setLoading(true);setErrors([]);
  const failures:string[]=[];
  const [postResult,myResult,teamResult,proposalResult,matchResult,notificationResult]=await Promise.allSettled([
   matchPostsService.list(),matchPostsService.mine(),teamsService.list(),proposalsService.list(),matchesService.list(),notificationsService.list()
  ]);
  if(postResult.status==='fulfilled')setPosts(postResult.value.data);else failures.push('Bảng tin: '+errorMessage(postResult.reason));
  if(myResult.status==='fulfilled')setMyPosts(myResult.value.data);else failures.push('Bài đăng của tôi: '+errorMessage(myResult.reason));
  if(teamResult.status==='fulfilled')setTeams(teamResult.value.data);else failures.push('Đội bóng: '+errorMessage(teamResult.reason));
  if(proposalResult.status==='fulfilled')setProposals(proposalResult.value.data);else failures.push('Đề xuất: '+errorMessage(proposalResult.reason));
  if(matchResult.status==='fulfilled')setMatches(matchResult.value.data);else failures.push('Trận đấu: '+errorMessage(matchResult.reason));
  if(notificationResult.status==='fulfilled')setNotifications(notificationResult.value.data);else failures.push('Thông báo: '+errorMessage(notificationResult.reason));
  setErrors(failures);setLoading(false);
 },[]);
 useEffect(()=>{void load();},[load]);
 const sourcePosts=mineOnly?myPosts:posts;
 const visiblePosts=useMemo(()=>sourcePosts.filter(p=>(postFilter==='ALL'||p.post_type===postFilter)&&(pitchFilter==='ALL'||p.pitch_type===pitchFilter)&&(skillFilter==='ALL'||p.skill_level===skillFilter)&&p.title.toLocaleLowerCase().includes(search.toLocaleLowerCase())&&(!fromDate||(p.match_time!==null&&p.match_time.slice(0,10)>=fromDate))&&(!toDate||(p.match_time!==null&&p.match_time.slice(0,10)<=toDate)),[sourcePosts,postFilter,pitchFilter,skillFilter,search,fromDate,toDate]);
 const setField = <K extends keyof ReturnType<typeof initialForm>,>(key: K, value: ReturnType<typeof initialForm>[K]) => setForm(old => ({ ...old, [key]: value }));
 async function createPost(event:FormEvent<HTMLFormElement>){
  event.preventDefault();setNotice('');setDetailError('');
  if(form.title.trim().length<1||form.title.trim().length>150){setDetailError('Tiêu đề cần từ 1 đến 150 ký tự.');return;}
  if(form.description.length>3000){setDetailError('Mô tả không được vượt quá 3000 ký tự.');return;}
  const hasTime=form.type!=='LOOK_FOR_TEAM';
  const matchTime=hasTime?asOffset(form.matchTime):undefined;const endTime=hasTime?asOffset(form.endTime):undefined;const expiry=asOffset(form.expiryTime);
  if(!expiry||Date.parse(expiry)<=Date.now()){setDetailError('Thời hạn bài đăng phải nằm trong tương lai.');return;}
  if(hasTime&&(!matchTime||!endTime||Date.parse(endTime)-Date.parse(matchTime)!==90*60000)){setDetailError('Thời gian trận đấu phải đủ 90 phút.');return;}
  if(hasTime&&Date.parse(expiry!)>Date.parse(matchTime!)){setDetailError('Bài đăng phải hết hạn trước hoặc tại giờ bắt đầu trận.');return;}
  if(form.type!=='LOOK_FOR_TEAM'&&!form.teamId){setDetailError('Chọn đội bóng cho loại bài này.');return;}
  if(form.type!=='LOOK_FOR_TEAM'&&!form.pitchType){setDetailError('Chọn loại sân.');return;}
  const body:PostCreate={post_type:form.type,title:form.title.trim(),description:form.description.trim()||undefined,skill_level:form.skill,expiry_time:expiry,
   ...(form.teamId?{team_id:Number(form.teamId)}:{}),...(form.pitchType?{pitch_type:form.pitchType as 'PITCH_5'|'PITCH_7'}:{}),
   ...(matchTime?{match_time:matchTime,end_time:endTime}:{}),
   ...(['FIND_OPPONENT','RECRUIT_MEMBERS'].includes(form.type)?{payment_rule:form.paymentRule}:{}),
   ...(form.type==='RECRUIT_MEMBERS'||form.type==='RANDOM_SQUAD'?{required_players:Number(form.requiredPlayers)}:{})};
  if((form.type==='RECRUIT_MEMBERS'||form.type==='RANDOM_SQUAD')&&(!Number.isInteger(Number(form.requiredPlayers))||Number(form.requiredPlayers)<1)){setDetailError('Số người cần tuyển phải là số nguyên dương.');return;}
  setBusy(-1);
  try{const result=await matchPostsService.create(body);setNotice('Đã tạo bài đăng “'+result.data.title+'”.');setShowCreate(false);setForm(initialForm());await load();}
  catch(e){setDetailError(errorMessage(e));}finally{setBusy(null);}
 }
 async function openPost(id:number){setPostDetail(null);setDetailError('');setEditingPost(false);try{const result=await matchPostsService.get(id);setPostDetail(result.data);setEditTitle(result.data.title);setEditDescription(result.data.description??'');}catch(e){setDetailError(errorMessage(e));}}
 async function updatePost(event:FormEvent<HTMLFormElement>){event.preventDefault();if(!postDetail)return;setBusy(postDetail.post_id);setDetailError('');try{const result=await matchPostsService.update(postDetail.post_id,{title:editTitle.trim(),description:editDescription.trim()});setPostDetail(result.data);setEditingPost(false);setNotice('Đã cập nhật bài đăng.');await load();}catch(e){setDetailError(errorMessage(e));}finally{setBusy(null);}}
 async function applyToPost(post:PostSummary){
  if(busy!==null)return;setBusy(post.post_id);setDetailError('');
  try{
   if(post.post_type==='RECRUIT_MEMBERS'&&post.team_id!==null){await teamsService.requestJoin(post.team_id);}
   else{await matchPostsService.requestParticipant(post.post_id);}
   setNotice('Đã gửi yêu cầu. Việc gia nhập đội/chốt ghép vẫn cần các bước xác nhận theo Backend.');
  }catch(e){setDetailError(errorMessage(e));}finally{setBusy(null);}
 }
 async function cancelPost(post:MatchPost){
  if(!window.confirm('Bạn chắc chắn muốn hủy bài đăng này?'))return;setBusy(post.post_id);setDetailError('');
  try{await matchPostsService.cancel(post.post_id,'Người đăng hủy bài');setNotice('Đã gửi yêu cầu hủy bài đăng.');setPostDetail(null);await load();}
  catch(e){setDetailError(errorMessage(e));}finally{setBusy(null);}
 }
 async function respond(id:number,decision:'ACCEPTED'|'DECLINED'){
  if(!window.confirm(decision==='ACCEPTED'?'Bạn xác nhận đồng ý đề xuất?':'Bạn chắc chắn muốn từ chối đề xuất?'))return;
  setBusy(id);setDetailError('');
  try{const result=await proposalsService.respond(id,decision);setProposalDetail(result.data);setNotice('Đã ghi nhận phản hồi. Proposal được chấp thuận không đồng nghĩa trận đã CONFIRMED.');await load();}
  catch(e){setDetailError(errorMessage(e));}finally{setBusy(null);}
 }
 async function openProposal(id:number){setProposalDetail(null);setDetailError('');try{const result=await proposalsService.get(id);setProposalDetail(result.data);}catch(e){setDetailError(errorMessage(e));}}
 async function openMatch(id:number){setMatchDetail(null);setDetailError('');try{const result=await matchesService.get(id);setMatchDetail(result.data);}catch(e){setDetailError(errorMessage(e));}}
 async function markRead(id:number){
  setBusy(id);try{const result=await notificationsService.markRead(id);setNotifications(old=>old.map(n=>n.notification_id===id?result.data:n));}
  catch(e){setDetailError(errorMessage(e));}finally{setBusy(null);}
 }
 return <section className="mm-page">
  <div className="account-eyebrow">KẾT NỐI TỪ SÂN CỎ</div><div className="account-page-heading"><div><h1>Ghép đội & tìm trận<span>.</span></h1><p>Tìm đối thủ, tuyển đồng đội và theo dõi quá trình xác nhận trận đấu.</p></div><div className="mm-heading-actions"><a className="account-secondary-button" href="#/schedule">Lịch thi đấu</a><button className="account-primary-button" onClick={()=>{setShowCreate(v=>!v);setDetailError('');}}>＋ Tạo bài đăng</button></div></div>
  {notice&&<div className="notice-success" role="status">{notice}</div>}{detailError&&<div className="notice-error" role="alert">{detailError}<button type="button" onClick={()=>setDetailError('')}>Đóng</button></div>}
  {showCreate&&<section className="profile-form-card mm-create-form"><div className="profile-form-heading"><div><h2>Tạo bài đăng tìm trận</h2><p>Form thay đổi theo loại bài đăng. Chỉ gửi các trường thuộc PostCreate.</p></div><button className="account-secondary-button" type="button" onClick={()=>setShowCreate(false)}>Đóng</button></div>
   <form className="profile-form" onSubmit={createPost}>
    <div className="form-row"><div className="form-field"><label htmlFor="post-type">Loại bài đăng</label><select id="post-type" value={form.type} onChange={e=>setField('type',e.target.value as PostType)}>{Object.entries(postNames).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
     <div className="form-field"><label htmlFor="post-team">Đội bóng {form.type==='LOOK_FOR_TEAM'?'(không bắt buộc)':'*'}</label><select id="post-team" value={form.teamId} onChange={e=>setField('teamId',e.target.value)}><option value="">Chọn đội</option>{teams.map(t=><option key={t.team_id} value={t.team_id}>{t.team_name}</option>)}</select></div></div>
    <div className="form-field"><label htmlFor="post-title">Tiêu đề</label><input id="post-title" maxLength={150} value={form.title} onChange={e=>setField('title',e.target.value)} required placeholder="VD: FC A tìm đối thủ sân 7 tối thứ Sáu"/></div>
    <div className="form-field"><label htmlFor="post-description">Mô tả</label><textarea id="post-description" maxLength={3000} rows={3} value={form.description} onChange={e=>setField('description',e.target.value)} placeholder="Thông tin bổ sung về trình độ, địa điểm, cách liên hệ…"/></div>
    <div className="form-row"><div className="form-field"><label htmlFor="post-skill">Trình độ</label><select id="post-skill" value={form.skill} onChange={e=>setField('skill',e.target.value as SkillLevel)}>{Object.entries(skillNames).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
     <div className="form-field"><label htmlFor="post-pitch">Loại sân {form.type==='LOOK_FOR_TEAM'?'(có thể bổ sung sau)':'*'}</label><select id="post-pitch" value={form.pitchType} onChange={e=>setField('pitchType',e.target.value as PitchType)}><option value="">Chưa chọn</option><option value="PITCH_5">Sân 5</option><option value="PITCH_7">Sân 7</option></select></div></div>
    {form.type!=='LOOK_FOR_TEAM'&&<div className="form-row"><div className="form-field"><label htmlFor="post-start">Giờ bắt đầu (giờ Việt Nam)</label><input id="post-start" type="datetime-local" value={form.matchTime} onChange={e=>{setField('matchTime',e.target.value);setField('endTime',localInput(new Date(new Date(e.target.value+':00+07:00').getTime()+90*60000)));}} required/></div><div className="form-field"><label htmlFor="post-end">Giờ kết thúc</label><input id="post-end" type="datetime-local" value={form.endTime} onChange={e=>setField('endTime',e.target.value)} required/></div></div>}
    <div className="form-field"><label htmlFor="post-expiry">Hạn nhận yêu cầu (giờ Việt Nam)</label><input id="post-expiry" type="datetime-local" value={form.expiryTime} onChange={e=>setField('expiryTime',e.target.value)} required/></div>
    {['FIND_OPPONENT','RECRUIT_MEMBERS'].includes(form.type)&&<div className="form-field"><label htmlFor="post-payment">Quy tắc chia tiền sân</label><select id="post-payment" value={form.paymentRule} onChange={e=>setField('paymentRule',e.target.value as TeamPaymentRule)}><option value="SPLIT_EQUAL">Chia đều</option><option value="LOSER_PAYS_REMAINDER">Đội thua trả phần còn lại</option></select></div>}
    {(form.type==='RECRUIT_MEMBERS'||form.type==='RANDOM_SQUAD')&&<div className="form-field"><label htmlFor="post-required">Số người cần tuyển / ghép</label><input id="post-required" type="number" min={1} step={1} value={form.requiredPlayers} onChange={e=>setField('requiredPlayers',e.target.value)}/></div>}
    <div className="profile-actions"><button type="button" className="account-secondary-button" onClick={()=>setForm(initialForm())}>Đặt lại</button><button className="account-primary-button" type="submit" disabled={busy!==null}>{busy===-1?'Đang đăng…':'Đăng bài'}</button></div>
   </form>
  </section>}
  <div className="mm-tabs" role="tablist">{tabs.map(t=><button key={t.id} role="tab" aria-selected={tab===t.id} className={tab===t.id?'active':''} onClick={()=>setTab(t.id)}>{t.label}</button>)}</div>
  {errors.length>0&&<div className="notice-error"><strong>Một số nguồn dữ liệu chưa tải được:</strong><ul>{errors.map((e,i)=><li key={i}>{e}</li>)}</ul><button onClick={()=>void load()}>Thử lại</button></div>}
  {loading?<div className="account-panel account-loading">Đang tải dữ liệu…</div>:<>
   {tab==='posts'&&<><div className="mm-toolbar"><input aria-label="Tìm bài đăng" placeholder="Tìm theo tiêu đề…" value={search} onChange={e=>setSearch(e.target.value)}/><select aria-label="Lọc loại bài" value={postFilter} onChange={e=>setPostFilter(e.target.value)}><option value="ALL">Tất cả loại bài</option>{Object.entries(postNames).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select><select aria-label="Lọc loại sân" value={pitchFilter} onChange={e=>setPitchFilter(e.target.value)}><option value="ALL">Tất cả loại sân</option><option value="PITCH_5">Sân 5</option><option value="PITCH_7">Sân 7</option></select><select aria-label="Lọc trình độ" value={skillFilter} onChange={e=>setSkillFilter(e.target.value)}><option value="ALL">Mọi trình độ</option>{Object.entries(skillNames).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select><label className="mm-checkbox"><input type="checkbox" checked={mineOnly} onChange={e=>setMineOnly(e.target.checked)}/> Bài của tôi</label><label className="mm-date-filter">Từ ngày <input type="date" value={fromDate} onChange={e=>setFromDate(e.target.value)}/></label><label className="mm-date-filter">Đến ngày <input type="date" value={toDate} onChange={e=>setToDate(e.target.value)}/></label></div>
    {visiblePosts.length===0?<Empty text="Chưa có bài đăng phù hợp."/>:<div className="mm-grid">{visiblePosts.map(p=><article className="mm-card" key={p.post_id}><div className="mm-card-top"><span className="mm-type">{postNames[p.post_type]}</span><span className="mm-status">{postStatuses[p.status]??p.status}</span></div><h3>{p.title}</h3><p>{skillNames[p.skill_level]} · {p.pitch_type?pitchNames[p.pitch_type]:'Chưa chọn sân'}</p><p>Thời gian: {dateLabel(p.match_time)}</p><p>Người tham gia: {p.current_players}{p.required_players?'/'+p.required_players:''}</p><small>Hết hạn: {dateLabel(p.expiry_time)}</small><div className="mm-actions"><button onClick={()=>void openPost(p.post_id)}>Chi tiết</button>{p.status==='OPEN'&&p.post_type!=='FIND_OPPONENT'&&<button className="secondary" disabled={busy!==null} onClick={()=>void applyToPost(p)}>{busy===p.post_id?'Đang gửi…':'Đăng ký tham gia'}</button>}</div></article>)}</div>}</>}
   {tab==='teams'&&(teams.length?<div className="mm-grid">{teams.map(t=><article className="mm-card" key={t.team_id}><span className="mm-type">{t.creation_type==='AI_RANDOM'?'Đội ghép tự động':'Đội của bạn'}</span><h3>{t.team_name}</h3><p>{t.active_member_count} thành viên</p><span className="mm-status">{t.status==='ACTIVE'?'Đang hoạt động':'Ngừng hoạt động'}</span><div className="mm-actions"><a className="mm-link-button" href="#/teams">Quản lý đội</a></div></article>)}</div>:<Empty text="Bạn chưa có đội bóng nào."/>)}
   {tab==='proposals'&&(proposals.length?<div className="mm-grid">{proposals.map(p=><article className="mm-card" key={p.proposal_id}><div className="mm-card-top"><span className="mm-type">{p.proposal_type==='OPPONENT'?'Ghép đối thủ':'Tuyển thành viên'}</span><span className="mm-status">{statusNames[p.status]??p.status}</span></div><h3>Đề xuất #{p.proposal_id}</h3><p>Mức độ phù hợp: {p.compatibility_score}%</p><p>Hết hạn: {dateLabel(p.expires_at)}</p><div className="mm-actions"><button onClick={()=>void openProposal(p.proposal_id)}>Chi tiết</button>{p.status==='PENDING_CONFIRMATION'&&<><button disabled={busy!==null} onClick={()=>void respond(p.proposal_id,'ACCEPTED')}>Đồng ý</button><button className="secondary" disabled={busy!==null} onClick={()=>void respond(p.proposal_id,'DECLINED')}>Từ chối</button></>}</div></article>)}</div>:<Empty text="Chưa có đề xuất ghép trận." />)}
   {tab==='matches'&&(matches.length?<div className="mm-grid">{matches.map(m=><article className="mm-card" key={m.match_id}><span className="mm-type">Trận #{m.match_id}</span><h3>{m.status==='CONFIRMED'?'Trận đã xác nhận':m.status==='SUGGESTED'?'Đang chờ xác nhận':'Trạng thái trận đấu'}</h3><p>Thời gian: {dateLabel(m.match_time)}</p><span className="mm-status">{statusNames[m.status]??m.status}</span><div className="mm-actions"><button onClick={()=>void openMatch(m.match_id)}>Chi tiết trận</button></div></article>)}</div>:<Empty text="Chưa có trận đấu nào." />)}
   {tab==='notifications'&&(notifications.length?<div className="mm-list">{notifications.map(n=><article className={n.is_read?'mm-notice':'mm-notice unread'} key={n.notification_id}><div><strong>{n.title}</strong><p>{n.content}</p><small>{dateLabel(n.created_at)} · {n.notification_type}</small></div><div className="mm-actions">{!n.is_read&&<button disabled={busy===n.notification_id} onClick={()=>void markRead(n.notification_id)}>Đánh dấu đã đọc</button>}{n.proposal_id&&<button className="secondary" onClick={()=>void openProposal(n.proposal_id!)}>Đến đề xuất</button>}{n.match_id&&<button className="secondary" onClick={()=>void openMatch(n.match_id!)}>Đến trận đấu</button>}</div></article>)}</div>:<Empty text="Bạn chưa có thông báo." />)}
  </>}
  {postDetail&&<section className="account-panel mm-detail"><div className="account-section-heading"><div><span className="mm-type">CHI TIẾT BÀI ĐĂNG</span><h2>{postDetail.title}</h2></div><button className="account-secondary-button" onClick={()=>setPostDetail(null)}>Đóng</button></div><p>{postNames[postDetail.post_type]} · {postStatuses[postDetail.status]??postDetail.status}</p><p>{postDetail.description||'Không có mô tả.'}</p>{myPosts.some(p=>p.post_id===postDetail.post_id)&&postDetail.status==='OPEN'&&<button className="account-secondary-button" onClick={()=>setEditingPost(v=>!v)}>Chỉnh sửa bài</button>}{editingPost&&<form className="profile-form" onSubmit={updatePost}><div className="form-field"><label htmlFor="edit-post-title">Tiêu đề</label><input id="edit-post-title" maxLength={150} value={editTitle} onChange={e=>setEditTitle(e.target.value)} required/></div><div className="form-field"><label htmlFor="edit-post-description">Mô tả</label><textarea id="edit-post-description" rows={3} maxLength={3000} value={editDescription} onChange={e=>setEditDescription(e.target.value)}/></div><button className="account-primary-button" disabled={busy!==null}>{busy===postDetail.post_id?'Đang lưu…':'Lưu bài đăng'}</button></form>}<p>Loại sân: {postDetail.pitch_type?pitchNames[postDetail.pitch_type]:'Chưa chọn'} · Trình độ: {skillNames[postDetail.skill_level]}</p><p>Giờ trận: {dateLabel(postDetail.match_time)} – {dateLabel(postDetail.end_time)}</p><p>AI có thể ghép: {postDetail.matching_ready?'Đủ thông tin bắt buộc':'Cần bổ sung thông tin'}</p>{myPosts.some(p=>p.post_id===postDetail.post_id)&&<button className="account-secondary-button" disabled={busy!==null||postDetail.status!=='OPEN'} onClick={()=>void cancelPost(postDetail)}>Hủy bài đăng</button>}</section>}
  {proposalDetail&&<section className="account-panel mm-detail"><div className="account-section-heading"><div><span className="mm-type">CHI TIẾT ĐỀ XUẤT</span><h2>Proposal #{proposalDetail.proposal_id}</h2></div><button className="account-secondary-button" onClick={()=>setProposalDetail(null)}>Đóng</button></div><p>Điểm phù hợp: {proposalDetail.compatibility_score}% · Trạng thái: {statusNames[proposalDetail.status]??proposalDetail.status}</p><p>Hạn phản hồi: {dateLabel(proposalDetail.expires_at)}</p><h3>Xác nhận của các bên</h3>{proposalDetail.confirmations.map(c=><div className="team-member-row" key={c.user_id}><strong>Người dùng #{c.user_id}</strong><span>{c.decision==='PENDING'?'Chưa phản hồi':c.decision==='ACCEPTED'?'Đồng ý':'Từ chối'} · {dateLabel(c.responded_at)}</span></div>)}{proposalDetail.status==='ACCEPTED'&&<div className="account-notice"><span>i</span><div><strong>Đã có đồng thuận</strong><p>Proposal ACCEPTED chưa chứng minh Booking đã hoàn tất. Chỉ Match CONFIRMED mới là trận chính thức.</p></div></div>}</section>}
  {matchDetail&&<section className="account-panel mm-detail"><div className="account-section-heading"><div><span className="mm-type">CHI TIẾT TRẬN ĐẤU</span><h2>Trận #{matchDetail.match_id}</h2></div><button className="account-secondary-button" onClick={()=>setMatchDetail(null)}>Đóng</button></div><p>{dateLabel(matchDetail.match_time)} – {dateLabel(matchDetail.end_time)}</p><p>Trạng thái: {statusNames[matchDetail.status]??matchDetail.status}</p><p>Đội tham gia: {matchDetail.teams.map(t=>t.team_name).join(' vs ')||'Backend chưa trả danh sách đội'}</p><p>Sân: {matchDetail.booking?'Sân #'+matchDetail.booking.pitch_id:'Chưa có booking được xác nhận'}</p><p>Booking: {matchDetail.booking?.status??'Chưa có'}</p></section>}
  <div className="mm-footnote">Không tự tính điểm AI, không tự tạo Booking hoặc giả lập thanh toán. Trận SUGGESTED được hiển thị riêng; lịch chính thức chỉ gồm CONFIRMED.</div>
 </section>;
}
function Empty({text}:{text:string}){return <div className="account-panel mm-empty"><span>◎</span><h3>{text}</h3><p>Khi có dữ liệu từ hệ thống, nội dung sẽ xuất hiện tại đây.</p></div>}
