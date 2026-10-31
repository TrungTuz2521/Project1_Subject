import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { session } from '../../stores/session';
import { logout } from '../../services/auth';
import { teamsService } from '../../services/teams';
import { matchPostsService } from '../../services/matchPosts';
import { errorMessage } from '../../services/api';
import type { Participant, Team, TeamDetail, MatchPost } from '../../types/api';

const timeLabel=(value:string)=>new Date(value).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'});
export function TeamsPage(){
 const current=session.getSnapshot();
 const [teams,setTeams]=useState<Team[]>([]); const [detail,setDetail]=useState<TeamDetail|null>(null);
 const [recruitment,setRecruitment]=useState<MatchPost|null>(null); const [applicants,setApplicants]=useState<Participant[]>([]);
 const [busy,setBusy]=useState(false); const [loading,setLoading]=useState(true); const [error,setError]=useState(''); const [notice,setNotice]=useState('');
 const [name,setName]=useState(''); const [editing,setEditing]=useState(false); const [creating,setCreating]=useState(false);
 const [revision,setRevision]=useState(0);
 const isCaptain=Boolean(detail?.members.some(m=>m.user_id===current?.user.user_id&&m.role==='CAPTAIN'&&m.status==='ACTIVE'));
 const isMember=Boolean(detail?.members.some(m=>m.user_id===current?.user.user_id&&m.status==='ACTIVE'));
 const canCreateTeam=current?.user.role==='PLAYER';
 async function loadList(){
  setLoading(true);setError('');
  try{const result=await teamsService.list(1);setTeams(result.data);}
  catch(e){setError(errorMessage(e));}finally{setLoading(false);}
 }
 useEffect(()=>{void loadList();},[revision]);
 async function openTeam(id:number){
  setLoading(true);setError('');setNotice('');setApplicants([]);setRecruitment(null);
  try{
   const pair=await Promise.all([teamsService.get(id),matchPostsService.mine()]);
   setDetail(pair[0].data);setName(pair[0].data.team_name);
   const post=pair[1].data.find(p=>p.team_id===id&&p.post_type==='RECRUIT_MEMBERS'&&p.status==='OPEN')??null;
   setRecruitment(post);
   if(post&&pair[0].data.members.some(m=>m.user_id===current?.user.user_id&&m.role==='CAPTAIN'&&m.status==='ACTIVE')){
    const result=await teamsService.listRecruitmentParticipants(post.post_id);
    setApplicants(result.data.filter(p=>p.status==='PENDING'));
   }
  }catch(e){setError(errorMessage(e));}finally{setLoading(false);}
 }
 async function submitTeam(event:FormEvent<HTMLFormElement>){
  event.preventDefault();const value=name.trim();
  if(value.length<1||value.length>100){setError('Tên đội phải từ 1 đến 100 ký tự.');return;}
  setBusy(true);setError('');setNotice('');
  try{
   if(detail){await teamsService.update(detail.team_id,{team_name:value});setNotice('Đã cập nhật tên đội.');await openTeam(detail.team_id);}
   else{const created=await teamsService.create({team_name:value});setNotice('Đã tạo đội mới. Bạn là đội trưởng.');setName('');setCreating(false);setRevision(v=>v+1);await openTeam(created.data.team_id);}
  }catch(e){setError(errorMessage(e));}finally{setBusy(false);}
 }
 async function handleApplicant(postId:number,decision:'ACCEPTED'|'DECLINED'){
  if(!detail||!window.confirm(decision==='ACCEPTED'?'Chấp thuận yêu cầu này? Ứng viên vẫn cần xác nhận đề xuất ghép.':'Từ chối yêu cầu tham gia đội?'))return;
  setBusy(true);setError('');setNotice('');
  try{await teamsService.respondJoinRequest(detail.team_id,postId,decision);setNotice('Đã ghi nhận phản hồi. Việc thêm thành viên chỉ hoàn tất sau khi hai bên xác nhận proposal.');await openTeam(detail.team_id);}
  catch(e){setError(errorMessage(e));}finally{setBusy(false);}
 }
 async function leaveTeam(){
  if(!detail||!window.confirm('Bạn chắc chắn muốn rời đội bóng này?'))return;
  setBusy(true);setError('');
  try{await teamsService.leave(detail.team_id);setNotice('Bạn đã rời đội.');setDetail(null);setRevision(v=>v+1);}
  catch(e){setError(errorMessage(e));}finally{setBusy(false);}
 }
 async function removeMember(userId:number){
  if(!detail||!window.confirm('Xóa thành viên này khỏi đội?'))return;
  setBusy(true);setError('');
  try{await teamsService.removeMember(detail.team_id,userId);setNotice('Đã gửi yêu cầu xóa thành viên.');await openTeam(detail.team_id);}
  catch(e){setError(errorMessage(e));}finally{setBusy(false);}
 }
 return <div className="account-shell">
  <aside className="account-sidebar"><a href="#/dashboard" className="account-brand"><span className="account-brand-mark">F</span><span>FOOTBALL<small>FIELD MANAGEMENT</small></span></a><div className="account-side-label">KHÔNG GIAN CỦA BẠN</div><nav className="account-nav" aria-label="Điều hướng chính"><a href="#/dashboard" className="account-nav-item"><span className="account-nav-icon">⌂</span><span>Tổng quan</span></a><a href="#/teams" className="account-nav-item active"><span className="account-nav-icon">♧</span><span>Đội bóng của tôi</span></a><a href="#/matchmaking" className="account-nav-item"><span className="account-nav-icon">⇄</span><span>Ghép đội & tìm trận</span></a><a href="#/schedule" className="account-nav-item"><span className="account-nav-icon">▦</span><span>Lịch thi đấu</span></a><a href="#/notifications" className="account-nav-item"><span className="account-nav-icon">♧</span><span>Thông báo</span></a><a href="#/profile" className="account-nav-item"><span className="account-nav-icon">◎</span><span>Hồ sơ cá nhân</span></a></nav><div className="account-sidebar-bottom"><div className="account-mini-pitch"><span/></div><p><i/> Cùng đội. Cùng đam mê.</p><small>Chọn đội, tìm kèo, ra sân.</small></div></aside>
  <div className="account-workspace"><header className="account-topbar"><div className="account-breadcrumb">Không gian cá nhân <span>/</span> <strong>Đội bóng</strong></div><div className="account-user"><span className="account-avatar">{current?.user.full_name.split(/\\s+/).slice(-2).map(x=>x[0]).join('').toUpperCase()}</span><span className="account-user-name">{current?.user.full_name}</span><a href="#/dashboard">Quay lại</a><button className="account-secondary-button" onClick={()=>{window.dispatchEvent(new Event('app:manual-logout'));logout();window.location.hash='/login';}}>Đăng xuất</button></div></header>
   <main className="account-main"><div className="account-eyebrow">QUẢN LÝ ĐỘI BÓNG</div><div className="account-page-heading"><div><h1>Đội bóng của tôi<span>.</span></h1><p>Tạo đội, quản lý thành viên và xử lý yêu cầu tuyển người.</p></div>{canCreateTeam&&<button className="account-primary-button" onClick={()=>{setDetail(null);setName('');setCreating(v=>!v);setError('');}}>＋ Tạo đội</button>}</div>
    {error&&<div className="notice-error" role="alert">{error}</div>}{notice&&<div className="notice-success" role="status">{notice}</div>}
    {creating&&canCreateTeam&&<section className="profile-form-card"><div className="profile-form-heading"><div><h2>Tạo đội bóng mới</h2><p>Bạn sẽ trở thành đội trưởng đội vừa tạo.</p></div></div><form className="profile-form" onSubmit={submitTeam}><div className="form-field"><label htmlFor="team-name">Tên đội bóng</label><input id="team-name" value={name} maxLength={100} onChange={e=>setName(e.target.value)} placeholder="Ví dụ: FC Chiều Thứ Bảy" required/></div><div className="profile-actions"><button className="account-secondary-button" type="button" onClick={()=>setCreating(false)}>Hủy</button><button className="account-primary-button" disabled={busy}>{busy?'Đang lưu…':'Tạo đội'}</button></div></form></section>}
    <div className="team-workspace">
     <section className="account-panel"><div className="account-section-heading"><div><h2>Danh sách đội bóng</h2><p>{teams.length} đội trong tài khoản</p></div><button className="account-secondary-button" onClick={()=>void loadList()} disabled={loading}>Làm mới</button></div>
      {loading&&!detail?<div className="account-loading">Đang tải đội bóng…</div>:teams.length===0?<div className="mm-empty"><h3>Bạn chưa có đội bóng</h3><p>Tạo đội đầu tiên hoặc đăng ký tham gia một đội qua bài tuyển thành viên.</p></div>:<div className="team-manager-list">{teams.map((team,index)=><button key={team.team_id} className={detail?.team_id===team.team_id?'team-manager-item active':'team-manager-item'} onClick={()=>void openTeam(team.team_id)}><span className={'team-manager-crest crest-'+(index%3)}>{team.team_name.split(' ').slice(0,2).map(x=>x[0]).join('').toUpperCase()}</span><span><strong>{team.team_name}</strong><small>{team.active_member_count} thành viên · {team.creation_type==='AI_RANDOM'?'Đội ghép tự động':'Đội do người chơi tạo'}</small></span><span className="team-manager-status">{team.status==='ACTIVE'?'Hoạt động':'Ngừng'}</span></button>)}</div>}
     </section>
     <section className="account-panel team-detail-panel">
      {!detail?<div className="mm-empty"><span>⚽</span><h3>Chọn một đội để xem chi tiết</h3><p>Thông tin đội, danh sách thành viên và yêu cầu tuyển dụng sẽ hiển thị tại đây.</p></div>:<>
       <div className="account-section-heading"><div><span className="mm-type">CHI TIẾT ĐỘI BÓNG</span><h2>{detail.team_name}</h2><p>{detail.active_member_count} thành viên · {detail.status==='ACTIVE'?'Đang hoạt động':'Ngừng hoạt động'}</p></div><button className="account-secondary-button" onClick={()=>setEditing(v=>!v)} disabled={!isCaptain}>Chỉnh sửa</button></div>
       {editing&&<form className="team-inline-edit" onSubmit={submitTeam}><input value={name} onChange={e=>setName(e.target.value)} maxLength={100} aria-label="Tên đội mới"/><button className="account-primary-button" disabled={busy}>Lưu</button></form>}
       <div className="team-members"><h3>Thành viên</h3>{detail.members.length===0?<p>Chưa có dữ liệu thành viên từ API.</p>:detail.members.map(member=><div className="team-member-row" key={member.user_id}><span className="account-avatar">{member.full_name.split(/\\s+/).slice(-2).map(x=>x[0]).join('').toUpperCase()}</span><div><strong>{member.full_name}</strong><small>{member.role==='CAPTAIN'?'Đội trưởng':'Thành viên'} · {member.status==='ACTIVE'?'Đang tham gia':member.status==='LEFT'?'Đã rời đội':'Đã bị xóa'} · {timeLabel(member.joined_at)}</small></div>{member.role!=='CAPTAIN'&&isCaptain&&member.status==='ACTIVE'&&<button className="account-secondary-button" disabled={busy} onClick={()=>void removeMember(member.user_id)}>Xóa</button>}</div>)}</div>
       {isCaptain&&<section className="team-requests"><div className="account-section-heading"><div><h3>Yêu cầu tuyển thành viên</h3><p>{recruitment?'Bài tuyển đang mở: '+recruitment.title:'Đội chưa có bài RECRUIT_MEMBERS đang mở.'}</p></div></div>{applicants.length===0?<p className="input-caption">Chưa có yêu cầu đang chờ xử lý.</p>:applicants.map(item=><div className="team-member-row" key={item.participant_id}><div><strong>Người chơi #{item.user_id}</strong><small>Đăng ký ngày {timeLabel(item.joined_at)}</small></div><div className="mm-actions"><button disabled={busy} onClick={()=>void handleApplicant(item.post_id,'ACCEPTED')}>Chấp thuận</button><button className="secondary" disabled={busy} onClick={()=>void handleApplicant(item.post_id,'DECLINED')}>Từ chối</button></div></div>)}</section>}
       <div className="team-detail-actions">{isMember&&!isCaptain&&current?.user.role==='PLAYER'&&<button className="account-secondary-button" onClick={()=>void leaveTeam()} disabled={busy}>Rời đội</button>}</div>
      </>}
     </section>
    </div>
   </main>
  </div>
 </div>;
}
