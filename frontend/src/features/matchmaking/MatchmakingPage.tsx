import { useCallback, useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { watchMatchmakingInbox } from '../../services/matchmakingInbox';
import { PostParticipationAction, acceptsParticipant } from './PostParticipationAction';
import { PostTimePicker } from './PostTimePicker';
import { SessionAttendancePicker } from './SessionAttendancePicker';
import { advanceDate, postStartOptions, vietnamDate } from './postSchedule';
import { matchPostsService } from '../../services/matchPosts';
import { proposalsService } from '../../services/proposals';
import { matchesService } from '../../services/matches';
import { notificationsService } from '../../services/notifications';
import { teamsService } from '../../services/teams';
import { formErrorMessage as errorMessage } from '../../services/formErrors';
import { session } from '../../stores/session';
import { bookingForNotification, bookingHash } from '../../services/bookingNavigation';
import type { Match, MatchDetail, MatchPost, Notification, NotificationType, PostCreate, PostSummary, PostType, Proposal, ProposalDetail, Team, PitchType, SkillLevel, TeamPaymentRule } from '../../types/api';

type Tab='posts'|'teams'|'proposals'|'matches'|'notifications';
const tabs:{id:Tab;label:string}[]=[{id:'posts',label:'Bảng tin bài đăng'},{id:'teams',label:'Đội bóng'},{id:'proposals',label:'Đề xuất ghép'},{id:'matches',label:'Trận đấu'},{id:'notifications',label:'Thông báo'}];
const postNames:Record<PostType,string>={FIND_OPPONENT:'Tìm đối thủ',RECRUIT_MEMBERS:'Tuyển thành viên',LOOK_FOR_TEAM:'Tìm đội',RANDOM_SQUAD:'Ghép đội ngẫu nhiên'};
const postStatuses:Record<string,string>={OPEN:'Đang mở',LOCKED:'Đang ghép',MATCHED:'Đã ghép',EXPIRED:'Hết hạn',CANCELLED:'Đã hủy',PENDING_DEPOSIT:'Chờ cọc'};
const statusNames:Record<string,string>={PENDING_CONFIRMATION:'Chờ xác nhận',ACCEPTED:'Hai bên đã đồng ý',REJECTED:'Đã từ chối',EXPIRED:'Hết hạn',SUGGESTED:'Chờ booking/cọc',CONFIRMED:'Đã xác nhận',COMPLETED:'Hoàn thành',CANCELLED:'Đã hủy'};
const notificationLabels:Record<NotificationType,string>={
 MATCH_PROPOSAL:'Có đề xuất ghép trận mới',PROPOSAL_ACCEPTED:'Đề xuất đã được hai bên đồng ý',PROPOSAL_REJECTED:'Đề xuất bị từ chối',
 BOOKING_HOLD:'Sân đang được giữ chỗ',BOOKING_CONFIRMED:'Đặt sân đã xác nhận',PAYMENT_SUCCESS:'Thanh toán thành công',
 TEAM_JOINED:'Thành viên đã được cập nhật',POST_EXPIRED:'Bài đăng đã hết hạn',PROPOSAL_EXPIRED:'Đề xuất đã hết hạn',
 MATCH_CONFIRMED:'Trận đấu đã xác nhận',MATCH_CANCELLED:'Trận đấu đã bị hủy',BOOKING_EXPIRED:'Thời gian giữ sân đã hết',
 REFUND_PROCESSING:'Đang xử lý hoàn tiền',REFUND_SUCCESS:'Hoàn tiền thành công',REFUND_FAILED:'Hoàn tiền thất bại'
};
const notificationGroups:Record<NotificationType,string>={
 MATCH_PROPOSAL:'Ghép trận',PROPOSAL_ACCEPTED:'Ghép trận',PROPOSAL_REJECTED:'Ghép trận',
 BOOKING_HOLD:'Đặt sân & thanh toán',BOOKING_CONFIRMED:'Đặt sân & thanh toán',PAYMENT_SUCCESS:'Đặt sân & thanh toán',
 TEAM_JOINED:'Đội bóng',POST_EXPIRED:'Bài đăng',PROPOSAL_EXPIRED:'Ghép trận',
 MATCH_CONFIRMED:'Trận đấu',MATCH_CANCELLED:'Trận đấu',BOOKING_EXPIRED:'Đặt sân & thanh toán',
 REFUND_PROCESSING:'Hoàn tiền',REFUND_SUCCESS:'Hoàn tiền',REFUND_FAILED:'Hoàn tiền'
};
const skillNames:Record<SkillLevel,string>={BEGINNER:'Mới chơi',AMATEUR:'Phong trào',INTERMEDIATE:'Trung bình',SEMI_PRO:'Bán chuyên',PRO:'Chuyên nghiệp'};
const pitchNames:Record<PitchType,string>={PITCH_5:'Sân 5',PITCH_7:'Sân 7',PITCH_11:'Sân 11'};
const dateLabel=(v:string|null|undefined)=>v?new Date(v).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'Chưa xác định';
const vietnamDay=(v:string)=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(v));
function localInput(date:Date){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(date);
 const val=(k:string)=>parts.find(p=>p.type===k)?.value??'00';
 return val('year')+'-'+val('month')+'-'+val('day')+'T'+val('hour')+':'+val('minute');
}
function asOffset(value:string){return value?value+':00+07:00':undefined;}
function initialForm(){const start=new Date(advanceDate(vietnamDate(),1)+'T18:00:00+07:00');const end=new Date(start.getTime()+90*60000);return {type:'FIND_OPPONENT' as PostType,title:'',description:'',teamId:'',pitchType:'PITCH_7' as PitchType,skill:'INTERMEDIATE' as SkillLevel,matchTime:localInput(start),endTime:localInput(end),expiryTime:localInput(new Date(start.getTime()-2*3600000)),paymentRule:'SPLIT_EQUAL' as TeamPaymentRule,requiredPlayers:'1',attendanceUserIds:session.getSnapshot()?[session.getSnapshot()!.user.user_id]:[],guestPlayers:'0'};}
export function MatchmakingPage({initialTab='posts',initialProposalId=null}:{initialTab?:Tab;initialProposalId?:number|null}){
 const current=session.getSnapshot();const isPlayer=current?.user.role==='PLAYER';const [tab,setTab]=useState<Tab>(initialTab);
 const [posts,setPosts]=useState<PostSummary[]>([]);const [myPosts,setMyPosts]=useState<MatchPost[]>([]);const [teams,setTeams]=useState<Team[]>([]);
 const [proposals,setProposals]=useState<Proposal[]>([]);const [matches,setMatches]=useState<Match[]>([]);const [notifications,setNotifications]=useState<Notification[]>([]);
 const [loading,setLoading]=useState(false);const [errors,setErrors]=useState<string[]>([]);const [busy,setBusy]=useState<number|null>(null);const [notice,setNotice]=useState('');
 const [search,setSearch]=useState('');const [postFilter,setPostFilter]=useState('ALL');const [pitchFilter,setPitchFilter]=useState('ALL');const [skillFilter,setSkillFilter]=useState('ALL');
 const [mineOnly,setMineOnly]=useState(false);const [fromDate,setFromDate]=useState('');const [toDate,setToDate]=useState('');const [showCreate,setShowCreate]=useState(false);const [form,setForm]=useState(initialForm);
 const [postDetail,setPostDetail]=useState<MatchPost|null>(null);const [proposalDetail,setProposalDetail]=useState<ProposalDetail|null>(null);const [matchDetail,setMatchDetail]=useState<MatchDetail|null>(null);
 const [editingPost,setEditingPost]=useState(false);const [editTitle,setEditTitle]=useState('');const [editDescription,setEditDescription]=useState('');
 const [editPitchType,setEditPitchType]=useState<PitchType|''>('');const [editSkill,setEditSkill]=useState<SkillLevel>('INTERMEDIATE');const [editMatchTime,setEditMatchTime]=useState('');const [editEndTime,setEditEndTime]=useState('');const [editExpiry,setEditExpiry]=useState('');const [editPaymentRule,setEditPaymentRule]=useState<TeamPaymentRule|''>('');const [editRequiredPlayers,setEditRequiredPlayers]=useState('');
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
 useEffect(()=>{setTab(initialTab);},[initialTab]);
 useEffect(()=>{void load();},[load]);
 useEffect(()=>{
  const inbox=watchMatchmakingInbox(data=>{
   if(data.notifications)setNotifications(data.notifications);
   if(data.proposals)setProposals(data.proposals);
  });
  return ()=>inbox.stop();
 },[]);
 useEffect(()=>{
  if(!initialProposalId)return;
  const controller=new AbortController();let active=true;
  setTab('proposals');setProposalDetail(null);setDetailError('');
  proposalsService.get(initialProposalId,controller.signal).then(result=>{if(active)setProposalDetail(result.data);})
   .catch(error=>{if(active)setDetailError(errorMessage(error));});
  return ()=>{active=false;controller.abort();};
 },[initialProposalId]);
 const sourcePosts=mineOnly?myPosts:posts;
 const visiblePosts=useMemo(()=>sourcePosts.filter(p=>(postFilter==='ALL'||p.post_type===postFilter)&&(pitchFilter==='ALL'||p.pitch_type===pitchFilter)&&(skillFilter==='ALL'||p.skill_level===skillFilter)&&p.title.toLocaleLowerCase().includes(search.toLocaleLowerCase())&&(!fromDate||(p.match_time!==null&&vietnamDay(p.match_time)>=fromDate))&&(!toDate||(p.match_time!==null&&vietnamDay(p.match_time)<=toDate))),[sourcePosts,postFilter,pitchFilter,skillFilter,search,fromDate,toDate]);
 const setField = <K extends keyof ReturnType<typeof initialForm>,>(key: K, value: ReturnType<typeof initialForm>[K]) => setForm(old => ({ ...old, [key]: value }));
 async function createPost(event:FormEvent<HTMLFormElement>){
  event.preventDefault();setNotice('');setDetailError('');
  if(!isPlayer){setDetailError('Chỉ người chơi mới được tạo bài đăng.');return;}
  if(form.title.trim().length<1||form.title.trim().length>150){setDetailError('Tiêu đề cần từ 1 đến 150 ký tự.');return;}
  if(form.description.length>3000){setDetailError('Mô tả không được vượt quá 3000 ký tự.');return;}
  const hasTime=form.type!=='LOOK_FOR_TEAM';
  const matchTime=hasTime?asOffset(form.matchTime):undefined;const endTime=hasTime?asOffset(form.endTime):undefined;const expiry=asOffset(form.expiryTime);
  if(!expiry||Date.parse(expiry)<=Date.now()){setDetailError('Thời hạn bài đăng phải nằm trong tương lai.');return;}
  if(hasTime&&(!matchTime||!endTime||Date.parse(endTime)-Date.parse(matchTime)!==90*60000)){setDetailError('Thời gian trận đấu phải đủ 90 phút.');return;}
  if(hasTime&&!postStartOptions(form.matchTime.slice(0,10)).includes(form.matchTime.slice(11,16))){setDetailError('Chọn lại một khung giờ còn hiệu lực trong danh sách.');return;}
  if(hasTime&&Date.parse(expiry!)>Date.parse(matchTime!)){setDetailError('Bài đăng phải hết hạn trước hoặc tại giờ bắt đầu trận.');return;}
  if(['FIND_OPPONENT','RECRUIT_MEMBERS'].includes(form.type)&&!form.teamId){setDetailError('Chọn đội bóng cho loại bài này.');return;}
  if(form.type!=='LOOK_FOR_TEAM'&&!form.pitchType){setDetailError('Chọn loại sân.');return;}
  const capacity=form.pitchType==='PITCH_5'?5:7;
  const guests=Number(form.guestPlayers);
  const attendance=form.attendanceUserIds;
  const total=attendance.length+guests;
  const missing=capacity-total;
  if(hasTime&&(!/^\d+$/.test(form.guestPlayers)||!Number.isInteger(guests)||guests<0||!attendance.includes(current!.user.user_id)||total>capacity)){setDetailError('Quân số buổi đá không hợp lệ. Không tính trùng người có tài khoản với người ngoài ứng dụng.');return;}
  if(form.type==='FIND_OPPONENT'&&missing!==0){setDetailError(`Buổi đá còn thiếu ${missing} người. Hãy chọn Tuyển thành viên trước.`);return;}
  if(['RECRUIT_MEMBERS','RANDOM_SQUAD'].includes(form.type)&&missing<=0){setDetailError('Buổi đá đã đủ người; hãy chọn Tìm đối thủ.');return;}
  const body:PostCreate={post_type:form.type,title:form.title.trim(),description:form.description.trim()||undefined,skill_level:form.skill,expiry_time:expiry,
   ...(hasTime?{attendance_user_ids:attendance,guest_players:guests}:{attendance_user_ids:[current!.user.user_id],guest_players:0}),
   ...(form.type==='LOOK_FOR_TEAM'?{team_id:null}:(form.teamId?{team_id:Number(form.teamId)}:{})),...(form.pitchType?{pitch_type:form.pitchType as 'PITCH_5'|'PITCH_7'}:{}),
   ...(matchTime?{match_time:matchTime,end_time:endTime}:{}),
   ...(['FIND_OPPONENT','RECRUIT_MEMBERS','RANDOM_SQUAD'].includes(form.type)?{payment_rule:form.paymentRule}:{}),
   ...(form.type==='RECRUIT_MEMBERS'||form.type==='RANDOM_SQUAD'?{required_players:missing}:{})};
  setBusy(-1);
  try{const result=await matchPostsService.create(body);setNotice('Đã tạo bài đăng “'+result.data.title+'”.');setShowCreate(false);setForm(initialForm());await load();}
  catch(e){setDetailError(errorMessage(e));}finally{setBusy(null);}
 }
 async function openPost(id:number){
  setPostDetail(null);setDetailError('');setEditingPost(false);
  try{
   const result=await matchPostsService.get(id);const post=result.data;setPostDetail(post);
   setEditTitle(post.title);setEditDescription(post.description??'');setEditPitchType(post.pitch_type??'');
   setEditSkill(post.skill_level);setEditMatchTime(post.match_time?localInput(new Date(post.match_time)):'');
   setEditEndTime(post.end_time?localInput(new Date(post.end_time)):'');setEditExpiry(localInput(new Date(post.expiry_time)));
   setEditPaymentRule(post.payment_rule??'');setEditRequiredPlayers(post.required_players===null?'':String(post.required_players));
  }catch(e){setDetailError(errorMessage(e));}
 }
 async function updatePost(event:FormEvent<HTMLFormElement>){
  event.preventDefault();if(!postDetail)return;setDetailError('');
  const expiry=asOffset(editExpiry);const matchTime=asOffset(editMatchTime);const endTime=asOffset(editEndTime);
  if(editTitle.trim().length<1||editTitle.trim().length>150){setDetailError('Tiêu đề cần từ 1 đến 150 ký tự.');return;}
  if(editDescription.length>3000){setDetailError('Mô tả tối đa 3000 ký tự.');return;}
  if(!expiry||Date.parse(expiry)<=Date.now()){setDetailError('Hạn bài đăng phải nằm trong tương lai.');return;}
  if(Boolean(matchTime)!==Boolean(endTime)){setDetailError('Cần nhập cả giờ bắt đầu và giờ kết thúc.');return;}
  if(matchTime&&endTime&&Date.parse(endTime)-Date.parse(matchTime)!==90*60000){setDetailError('Thời gian trận đấu phải đủ 90 phút.');return;}
  if(matchTime&&!postStartOptions(editMatchTime.slice(0,10)).includes(editMatchTime.slice(11,16))){setDetailError('Chọn lại một khung giờ còn hiệu lực trong danh sách.');return;}
  if(matchTime&&Date.parse(expiry)>Date.parse(matchTime)){setDetailError('Bài đăng phải hết hạn trước hoặc tại giờ bắt đầu trận.');return;}
  if(editRequiredPlayers.trim()&&(!Number.isInteger(Number(editRequiredPlayers))||Number(editRequiredPlayers)<1)){setDetailError('Số người cần tuyển phải là số nguyên dương.');return;}
  const body:Partial<PostCreate>={title:editTitle.trim(),description:editDescription.trim(),skill_level:editSkill,expiry_time:expiry,
   ...(editPitchType?{pitch_type:editPitchType as 'PITCH_5'|'PITCH_7'}:{}),
   ...(matchTime&&endTime?{match_time:matchTime,end_time:endTime}:{}),
   ...(editPaymentRule?{payment_rule:editPaymentRule}:{}),
   ...(editRequiredPlayers.trim()?{required_players:Number(editRequiredPlayers)}:{})};
  setBusy(postDetail.post_id);
  try{const result=await matchPostsService.update(postDetail.post_id,body);setPostDetail(result.data);setEditingPost(false);setNotice('Đã cập nhật bài đăng.');await load();}
  catch(e){setDetailError(errorMessage(e));}finally{setBusy(null);}
 }
 async function applyToPost(post:PostSummary){
  if(busy!==null)return;
  if(!isPlayer||myPosts.some(p=>p.post_id===post.post_id)||!acceptsParticipant(post)){setDetailError('Chỉ có thể đăng ký bài Tuyển thành viên còn mở và còn thiếu người.');return;}
  setBusy(post.post_id);setDetailError('');
  try{
   await matchPostsService.requestParticipant(post.post_id);
   setNotice('Đã gửi đăng ký. Chờ đội trưởng duyệt; bạn không cần xác nhận lại.');
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
  try{const result=await proposalsService.respond(id,decision);setProposalDetail(result.data);setNotice(result.data.proposal_type==='TEAM_MEMBER'&&result.data.status==='ACCEPTED'?'Đã duyệt và thêm thành viên vào đội.':'Đã ghi nhận phản hồi đề xuất.');await load();}
  catch(e){setDetailError(errorMessage(e));}finally{setBusy(null);}
 }
 async function openProposal(id:number){setProposalDetail(null);setDetailError('');try{const result=await proposalsService.get(id);setProposalDetail(result.data);}catch(e){setDetailError(errorMessage(e));}}
 async function openMatch(id:number){setMatchDetail(null);setDetailError('');try{const result=await matchesService.get(id);setMatchDetail(result.data);}catch(e){setDetailError(errorMessage(e));}}
 async function payNotification(notification:Notification){
  if(busy!==null)return;setBusy(notification.notification_id);setDetailError('');
  try{window.location.hash=bookingHash(await bookingForNotification(notification));}
  catch(error){setDetailError(errorMessage(error));}finally{setBusy(null);}
 }
 async function markRead(id:number){
  setBusy(id);try{const result=await notificationsService.markRead(id);setNotifications(old=>old.map(n=>n.notification_id===id?result.data:n));}
  catch(e){setDetailError(errorMessage(e));}finally{setBusy(null);}
 }
 const proposalSourcePost = proposalDetail ? posts.find(post => post.post_id === proposalDetail.source_post_id) : undefined;
 const proposalTargetPost = proposalDetail?.target_post_id ? posts.find(post => post.post_id === proposalDetail.target_post_id) : undefined;
 const proposalSourceTeam = proposalSourcePost?.team_id ? teams.find(team => team.team_id === proposalSourcePost.team_id) : undefined;
 const proposalTargetTeam = proposalTargetPost?.team_id ? teams.find(team => team.team_id === proposalTargetPost.team_id) : undefined;
 const directRecruitment = proposalDetail?.proposal_type==='TEAM_MEMBER'&&proposalDetail.candidate_user_id!==null&&proposalDetail.target_post_id===null;
 const isWaitingApplicant = directRecruitment&&proposalDetail?.candidate_user_id===current?.user.user_id&&proposalDetail.status==='PENDING_CONFIRMATION';
 const canRespondToProposal = !isWaitingApplicant&&Boolean(proposalDetail?.confirmations.some(
  confirmation => confirmation.user_id === current?.user.user_id && confirmation.decision === 'PENDING',
 ));
 const teamLabelForPost=(postId:number|null)=>{if(postId===null)return 'Cá nhân';const post=posts.find(item=>item.post_id===postId);if(!post)return 'Bài #'+postId;if(post.team_id===null)return post.title;return teams.find(team=>team.team_id===post.team_id)?.team_name??('Đội #'+post.team_id);};
 return <section className="mm-page">
  <div className="account-eyebrow">KẾT NỐI TỪ SÂN CỎ</div><div className="account-page-heading"><div><h1>Ghép đội & tìm trận<span>.</span></h1><p>Tìm đối thủ, tuyển đồng đội và theo dõi quá trình xác nhận trận đấu.</p></div><div className="mm-heading-actions"><button className="account-secondary-button" disabled={loading} onClick={()=>void load()}>Làm mới</button><a className="account-secondary-button" href="#/schedule">Lịch thi đấu</a>{isPlayer&&<button className="account-primary-button" onClick={()=>{setShowCreate(v=>!v);setDetailError('');}}>＋ Tạo bài đăng</button>}</div></div>
  {notice&&<div className="notice-success" role="status">{notice}</div>}{detailError&&<div className="notice-error" role="alert">{detailError}<button type="button" onClick={()=>setDetailError('')}>Đóng</button></div>}
  {showCreate&&isPlayer&&<section className="profile-form-card mm-create-form"><div className="profile-form-heading"><div><h2>Tạo bài đăng tìm trận</h2><p>Khai báo quân số cho buổi đá này; không cần thay đổi danh sách thành viên đội.</p></div><button className="account-secondary-button" type="button" onClick={()=>setShowCreate(false)}>Đóng</button></div>
   <form className="profile-form" onSubmit={createPost}>
    <div className="form-row"><div className="form-field"><label htmlFor="post-type">Loại bài đăng</label><select id="post-type" value={form.type} onChange={e=>{const next=e.target.value as PostType;setField('type',next);if(next==='LOOK_FOR_TEAM'){setField('teamId','');setField('pitchType','' as PitchType);}}}>{Object.entries(postNames).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
     {form.type!=='LOOK_FOR_TEAM'&&<div className="form-field"><label htmlFor="post-team">Đội bóng {form.type==='RANDOM_SQUAD'?'(có thể để trống)':'*'}</label><select id="post-team" value={form.teamId} onChange={e=>setForm(old=>({...old,teamId:e.target.value,attendanceUserIds:[current!.user.user_id],guestPlayers:'0'}))}><option value="">Chọn đội</option>{teams.map(t=><option key={t.team_id} value={t.team_id}>{t.team_name}</option>)}</select></div>}</div>
    <div className="form-field"><label htmlFor="post-title">Tiêu đề</label><input id="post-title" maxLength={150} value={form.title} onChange={e=>setField('title',e.target.value)} required placeholder="VD: FC A tìm đối thủ sân 7 tối thứ Sáu"/></div>
    <div className="form-field"><label htmlFor="post-description">Mô tả</label><textarea id="post-description" maxLength={3000} rows={3} value={form.description} onChange={e=>setField('description',e.target.value)} placeholder="Thông tin bổ sung về trình độ, địa điểm, cách liên hệ…"/></div>
    <div className="form-row"><div className="form-field"><label htmlFor="post-skill">Trình độ</label><select id="post-skill" value={form.skill} onChange={e=>setField('skill',e.target.value as SkillLevel)}>{Object.entries(skillNames).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
     <div className="form-field"><label htmlFor="post-pitch">Loại sân {form.type==='LOOK_FOR_TEAM'?'(có thể bổ sung sau)':'*'}</label><select id="post-pitch" value={form.pitchType} onChange={e=>setField('pitchType',e.target.value as PitchType)}><option value="">Chưa chọn</option><option value="PITCH_5">Sân 5</option><option value="PITCH_7">Sân 7</option></select></div></div>
    {form.type!=='LOOK_FOR_TEAM'&&<SessionAttendancePicker teamId={form.teamId} userId={current!.user.user_id} userName={current!.user.full_name} capacity={form.pitchType==='PITCH_5'?5:7}
      userIds={form.attendanceUserIds} guests={form.guestPlayers} onUsers={ids=>setField('attendanceUserIds',ids)} onGuests={count=>setField('guestPlayers',count)} />}
    {form.type!=='LOOK_FOR_TEAM'&&<PostTimePicker value={form.matchTime} onChange={(start,end)=>setForm(old=>({...old,matchTime:start,endTime:end}))}/> }
    <div className="form-field"><label htmlFor="post-expiry">Hạn nhận yêu cầu (giờ Việt Nam)</label><input id="post-expiry" type="datetime-local" value={form.expiryTime} onChange={e=>setField('expiryTime',e.target.value)} required/></div>
    {['FIND_OPPONENT','RECRUIT_MEMBERS','RANDOM_SQUAD'].includes(form.type)&&<div className="form-field"><label htmlFor="post-payment">Quy tắc chia tiền sân</label><select id="post-payment" value={form.paymentRule} onChange={e=>setField('paymentRule',e.target.value as TeamPaymentRule)}><option value="SPLIT_EQUAL">Chia đều</option><option value="LOSER_PAYS_REMAINDER">Đội thua trả phần còn lại</option></select></div>}
    {(form.type==='RECRUIT_MEMBERS'||form.type==='RANDOM_SQUAD')&&<div className="form-field"><label htmlFor="post-required">Số người còn thiếu (tự tính)</label><input id="post-required" type="number" min={1} step={1} value={Math.max(0,(form.pitchType==='PITCH_5'?5:7)-form.attendanceUserIds.length-Number(form.guestPlayers||0))} readOnly/></div>}
    <div className="profile-actions"><button type="button" className="account-secondary-button" onClick={()=>setForm(initialForm())}>Đặt lại</button><button className="account-primary-button" type="submit" disabled={busy!==null}>{busy===-1?'Đang đăng…':'Đăng bài'}</button></div>
   </form>
  </section>}
  <div className="mm-tabs" role="tablist">{tabs.map(t=><button key={t.id} role="tab" aria-selected={tab===t.id} className={tab===t.id?'active':''} onClick={()=>{setTab(t.id);if(t.id==='notifications'||t.id==='proposals')void load();}}>{t.label}{t.id==='notifications'&&notifications.some(n=>!n.is_read)?' ('+notifications.filter(n=>!n.is_read).length+')':''}</button>)}</div>
  {errors.length>0&&<div className="notice-error"><strong>Một số nguồn dữ liệu chưa tải được:</strong><ul>{errors.map((e,i)=><li key={i}>{e}</li>)}</ul><button onClick={()=>void load()}>Thử lại</button></div>}
  {loading?<div className="account-panel account-loading">Đang tải dữ liệu…</div>:<>
   {tab==='posts'&&<><div className="mm-toolbar"><input aria-label="Tìm bài đăng" placeholder="Tìm theo tiêu đề…" value={search} onChange={e=>setSearch(e.target.value)}/><select aria-label="Lọc loại bài" value={postFilter} onChange={e=>setPostFilter(e.target.value)}><option value="ALL">Tất cả loại bài</option>{Object.entries(postNames).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select><select aria-label="Lọc loại sân" value={pitchFilter} onChange={e=>setPitchFilter(e.target.value)}><option value="ALL">Tất cả loại sân</option><option value="PITCH_5">Sân 5</option><option value="PITCH_7">Sân 7</option></select><select aria-label="Lọc trình độ" value={skillFilter} onChange={e=>setSkillFilter(e.target.value)}><option value="ALL">Mọi trình độ</option>{Object.entries(skillNames).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select><label className="mm-checkbox"><input type="checkbox" checked={mineOnly} onChange={e=>setMineOnly(e.target.checked)}/> Bài của tôi</label><label className="mm-date-filter">Từ ngày <input type="date" value={fromDate} onChange={e=>setFromDate(e.target.value)}/></label><label className="mm-date-filter">Đến ngày <input type="date" value={toDate} onChange={e=>setToDate(e.target.value)}/></label></div>
    {visiblePosts.length===0?<Empty text="Chưa có bài đăng phù hợp."/>:<div className="mm-grid">{visiblePosts.map(p=><article className="mm-card" key={p.post_id}><div className="mm-card-top"><span className="mm-type">{postNames[p.post_type]}</span><span className="mm-status">{postStatuses[p.status]??p.status}</span></div><h3>{p.title}</h3><p>{skillNames[p.skill_level]} · {p.pitch_type?pitchNames[p.pitch_type]:'Chưa chọn sân'}</p><p>Thời gian: {dateLabel(p.match_time)}</p><p>Quân số buổi đá: {p.current_players}/{p.pitch_type==='PITCH_5'?5:7} người{p.required_players?` · Còn thiếu ${p.required_players}`:''}</p><small>{p.registered_players??p.current_players} người có tài khoản + {p.guest_players??0} người ngoài ứng dụng</small><small>Hết hạn: {dateLabel(p.expiry_time)}</small><div className="mm-actions"><button onClick={()=>void openPost(p.post_id)}>Chi tiết</button><PostParticipationAction post={p} isPlayer={isPlayer} isOwner={myPosts.some(mine=>mine.post_id===p.post_id)} busy={busy} onApply={post=>void applyToPost(post)}/></div></article>)}</div>}</>}
   {tab==='teams'&&(teams.length?<div className="mm-grid">{teams.map(t=><article className="mm-card" key={t.team_id}><span className="mm-type">{t.creation_type==='AI_RANDOM'?'Đội ghép tự động':'Đội của bạn'}</span><h3>{t.team_name}</h3><p>{t.active_member_count} thành viên</p><span className="mm-status">{t.status==='ACTIVE'?'Đang hoạt động':'Ngừng hoạt động'}</span><div className="mm-actions"><a className="mm-link-button" href="#/teams">Quản lý đội</a></div></article>)}</div>:<Empty text="Bạn chưa có đội bóng nào."/>)}
   {tab==='proposals'&&(proposals.length?<div className="mm-grid">{proposals.map(p=><article className="mm-card" key={p.proposal_id}><div className="mm-card-top"><span className="mm-type">{p.proposal_type==='OPPONENT'?'Ghép đối thủ':'Tuyển thành viên'}</span><span className="mm-status">{statusNames[p.status]??p.status}</span></div><h3>Đề xuất #{p.proposal_id}</h3><p>Mức độ phù hợp: {p.compatibility_score}%</p><p>Hai bên: <strong>{teamLabelForPost(p.source_post_id)}</strong>{p.proposal_type==='OPPONENT'?' vs ': ' · '}<strong>{p.target_post_id!==null?teamLabelForPost(p.target_post_id):'Người chơi #'+p.candidate_user_id}</strong></p><p>Hết hạn: {dateLabel(p.expires_at)}</p><div className="mm-actions"><button onClick={()=>void openProposal(p.proposal_id)}>Chi tiết & xác nhận</button></div></article>)}</div>:<Empty text="Chưa có đề xuất ghép trận." />)}
   {tab==='matches'&&(matches.length?<div className="mm-grid">{matches.map(m=><article className="mm-card" key={m.match_id}><span className="mm-type">Trận #{m.match_id}</span><h3>{m.status==='CONFIRMED'?'Trận đã xác nhận':m.status==='SUGGESTED'?'Đang chờ xác nhận':'Trạng thái trận đấu'}</h3><p>Hai đội: <strong>{teamLabelForPost(m.post_id)}</strong>{m.opponent_post_id!==null?' vs '+teamLabelForPost(m.opponent_post_id):''}</p><p>Thời gian: {dateLabel(m.match_time)}</p><span className="mm-status">{statusNames[m.status]??m.status}</span><div className="mm-actions"><button onClick={()=>void openMatch(m.match_id)}>Chi tiết trận</button></div></article>)}</div>:<Empty text="Chưa có trận đấu nào." />)}
   {tab==='notifications'&&(notifications.length?<div className="mm-list">{notifications.map(n=><article className={n.is_read?'mm-notice':'mm-notice unread'} key={n.notification_id}><div><strong>{n.title}</strong><p>{n.content}</p><small>{dateLabel(n.created_at)} · {notificationGroups[n.notification_type]} · {notificationLabels[n.notification_type]}</small></div><div className="mm-actions">{n.notification_type==='BOOKING_HOLD'&&<button disabled={busy!==null} onClick={()=>void payNotification(n)}>{busy===n.notification_id?'Đang mở booking…':'Thanh toán tiền cọc'}</button>}{!n.is_read&&<button disabled={busy===n.notification_id} onClick={()=>void markRead(n.notification_id)}>Đánh dấu đã đọc</button>}{n.proposal_id&&<button className="secondary" onClick={()=>void openProposal(n.proposal_id!)}>Đến đề xuất</button>}{n.match_id&&<button className="secondary" onClick={()=>void openMatch(n.match_id!)}>Đến trận đấu</button>}</div></article>)}</div>:<Empty text="Bạn chưa có thông báo." />)}
  </>}
  {postDetail&&<section className="account-panel mm-detail"><div className="account-section-heading"><div><span className="mm-type">CHI TIẾT BÀI ĐĂNG</span><h2>{postDetail.title}</h2></div><button className="account-secondary-button" onClick={()=>setPostDetail(null)}>Đóng</button></div><p>{postNames[postDetail.post_type]} · {postStatuses[postDetail.status]??postDetail.status}</p><p>{postDetail.description||'Không có mô tả.'}</p>{myPosts.some(p=>p.post_id===postDetail.post_id)&&postDetail.status==='OPEN'&&<button className="account-secondary-button" onClick={()=>setEditingPost(v=>!v)}>Chỉnh sửa bài</button>}{editingPost&&<form className="profile-form" onSubmit={updatePost}>
   <div className="form-field"><label htmlFor="edit-post-title">Tiêu đề</label><input id="edit-post-title" maxLength={150} value={editTitle} onChange={e=>setEditTitle(e.target.value)} required/></div>
   <div className="form-field"><label htmlFor="edit-post-description">Mô tả</label><textarea id="edit-post-description" rows={3} maxLength={3000} value={editDescription} onChange={e=>setEditDescription(e.target.value)}/></div>
   <div className="form-row"><div className="form-field"><label htmlFor="edit-post-skill">Trình độ</label><select id="edit-post-skill" value={editSkill} onChange={e=>setEditSkill(e.target.value as SkillLevel)}>{Object.entries(skillNames).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
    <div className="form-field"><label htmlFor="edit-post-pitch">Loại sân</label><select id="edit-post-pitch" value={editPitchType} onChange={e=>setEditPitchType(e.target.value as PitchType|'')}><option value="">Chưa chọn</option><option value="PITCH_5">Sân 5</option><option value="PITCH_7">Sân 7</option></select></div></div>
   <PostTimePicker idPrefix="edit-post" required={postDetail.post_type!=='LOOK_FOR_TEAM'} value={editMatchTime} onChange={(start,end)=>{setEditMatchTime(start);setEditEndTime(end);}} />
   <div className="form-field"><label htmlFor="edit-post-expiry">Hạn nhận yêu cầu</label><input id="edit-post-expiry" type="datetime-local" value={editExpiry} onChange={e=>setEditExpiry(e.target.value)} required/></div>
   {['FIND_OPPONENT','RECRUIT_MEMBERS'].includes(postDetail.post_type)&&<div className="form-field"><label htmlFor="edit-post-payment">Quy tắc chia tiền</label><select id="edit-post-payment" value={editPaymentRule} onChange={e=>setEditPaymentRule(e.target.value as TeamPaymentRule|'')}><option value="">Chưa chọn</option><option value="SPLIT_EQUAL">Chia đều</option><option value="LOSER_PAYS_REMAINDER">Đội thua trả phần còn lại</option></select></div>}
   {['RECRUIT_MEMBERS','RANDOM_SQUAD'].includes(postDetail.post_type)&&<div className="form-field"><label htmlFor="edit-post-required">Số người còn thiếu (tự tính)</label><input id="edit-post-required" type="number" min={1} step={1} value={editRequiredPlayers} onChange={e=>setEditRequiredPlayers(e.target.value)}/></div>}
   <button className="account-primary-button" disabled={busy!==null}>{busy===postDetail.post_id?'Đang lưu…':'Lưu thay đổi'}</button>
  </form>}<p>Quân số buổi đá: {postDetail.current_players}/{postDetail.pitch_type==='PITCH_5'?5:7} người — {postDetail.registered_players??postDetail.current_players} người có tài khoản + {postDetail.guest_players??0} người ngoài ứng dụng.</p><p>Loại sân: {postDetail.pitch_type?pitchNames[postDetail.pitch_type]:'Chưa chọn'} · Trình độ: {skillNames[postDetail.skill_level]}</p><p>Giờ trận: {dateLabel(postDetail.match_time)} – {dateLabel(postDetail.end_time)}</p><p>AI có thể ghép: {postDetail.matching_ready?'Đủ thông tin bắt buộc':'Cần bổ sung thông tin'}</p>{myPosts.some(p=>p.post_id===postDetail.post_id)&&postDetail.post_type==='RECRUIT_MEMBERS'&&postDetail.status==='MATCHED'&&postDetail.current_players>=(postDetail.pitch_type==='PITCH_5'?5:7)&&<button className="account-primary-button" onClick={()=>{
    setForm({...initialForm(),type:'FIND_OPPONENT',title:postDetail.title,teamId:String(postDetail.team_id),pitchType:postDetail.pitch_type??'PITCH_7',skill:postDetail.skill_level,
      matchTime:postDetail.match_time?localInput(new Date(postDetail.match_time)):initialForm().matchTime,endTime:postDetail.end_time?localInput(new Date(postDetail.end_time)):initialForm().endTime,
      expiryTime:localInput(new Date(postDetail.expiry_time)),paymentRule:postDetail.payment_rule??'SPLIT_EQUAL',attendanceUserIds:postDetail.attendance_user_ids??[current!.user.user_id],guestPlayers:String(postDetail.guest_players??0)});
    setShowCreate(true);setDetailError('');window.scrollTo({top:0,behavior:'smooth'});
  }}>Tạo bài tìm đối thủ với quân số này</button>}{myPosts.some(p=>p.post_id===postDetail.post_id)&&<button className="account-secondary-button" disabled={busy!==null||postDetail.status!=='OPEN'} onClick={()=>void cancelPost(postDetail)}>Hủy bài đăng</button>}</section>}
  {proposalDetail&&<section className="account-panel mm-detail"><div className="account-section-heading"><div><span className="mm-type">CHI TIẾT ĐỀ XUẤT</span><h2>Proposal #{proposalDetail.proposal_id}</h2></div><button className="account-secondary-button" onClick={()=>setProposalDetail(null)}>Đóng</button></div><p>Điểm phù hợp: {proposalDetail.compatibility_score}% · Trạng thái: {statusNames[proposalDetail.status]??proposalDetail.status}</p><p>Hạn phản hồi: {dateLabel(proposalDetail.expires_at)}</p><p>Hai bên: <strong>{proposalSourceTeam?.team_name??('Bài #'+proposalDetail.source_post_id)}</strong>{proposalDetail.proposal_type==='OPPONENT'?' vs ': ' · '}<strong>{proposalTargetTeam?.team_name??(proposalDetail.candidate_user_id!==null?'Người chơi #'+proposalDetail.candidate_user_id:proposalDetail.target_post_id?'Bài #'+proposalDetail.target_post_id:'Ứng viên')}</strong></p><h3>Xác nhận của các bên</h3>{proposalDetail.confirmations.map(c=><div className="team-member-row" key={c.user_id}><strong>Người dùng #{c.user_id}</strong><span>{c.decision==='PENDING'?'Chưa phản hồi':c.decision==='ACCEPTED'?'Đồng ý':'Từ chối'} · {dateLabel(c.responded_at)}</span></div>)}{isWaitingApplicant&&<p role="status">Bạn đã đăng ký tham gia. Đang chờ đội trưởng duyệt, không cần xác nhận lại.</p>}{canRespondToProposal&&proposalDetail.status==='PENDING_CONFIRMATION'&&<div className="mm-actions"><button disabled={busy!==null} onClick={()=>void respond(proposalDetail.proposal_id,'ACCEPTED')}>{directRecruitment?'Chấp nhận thành viên':'Đồng ý đề xuất'}</button><button className="secondary" disabled={busy!==null} onClick={()=>void respond(proposalDetail.proposal_id,'DECLINED')}>Từ chối</button></div>}{proposalDetail.status==='ACCEPTED'&&<div className="account-notice"><span>i</span><div><strong>{proposalDetail.proposal_type==='TEAM_MEMBER'?'Đã thêm thành viên':'Đã có đồng thuận'}</strong><p>{proposalDetail.proposal_type==='TEAM_MEMBER'?'Thành viên và quân số buổi đá đã được cập nhật.':'Proposal ACCEPTED chưa chứng minh Booking đã hoàn tất. Chỉ Match CONFIRMED mới là trận chính thức.'}</p></div></div>}</section>}
  {matchDetail&&<section className="account-panel mm-detail"><div className="account-section-heading"><div><span className="mm-type">CHI TIẾT TRẬN ĐẤU</span><h2>Trận #{matchDetail.match_id}</h2></div><button className="account-secondary-button" onClick={()=>setMatchDetail(null)}>Đóng</button></div><p>{dateLabel(matchDetail.match_time)} – {dateLabel(matchDetail.end_time)}</p><p>Trạng thái: {statusNames[matchDetail.status]??matchDetail.status}</p><p>Đội tham gia: {matchDetail.teams.map(t=>t.team_name).join(' vs ')||'Backend chưa trả danh sách đội'}</p><p>Sân: {matchDetail.booking?'Sân #'+matchDetail.booking.pitch_id:'Chưa có booking được xác nhận'}</p><p>Booking: {matchDetail.booking?.status??'Chưa có'}</p></section>}
  <div className="mm-footnote">Không tự tính điểm AI, không tự tạo Booking hoặc giả lập thanh toán. Trận SUGGESTED được hiển thị riêng; lịch chính thức chỉ gồm CONFIRMED.</div>
 </section>;
}
function Empty({text}:{text:string}){return <div className="account-panel mm-empty"><span>◎</span><h3>{text}</h3><p>Khi có dữ liệu từ hệ thống, nội dung sẽ xuất hiện tại đây.</p></div>}
