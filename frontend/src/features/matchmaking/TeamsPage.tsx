import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { session } from '../../stores/session';
import { teamsService } from '../../services/teams';
import { errorMessage } from '../../services/api';
import type { Team } from '../../types/api';

// A team is its name and its captain, the one who books. The head count is given with each opponent request.
const headCount=(team:Team)=>team.last_player_count===null?'Chưa tìm đối lần nào':`Lần trước ${team.last_player_count} người đi đá`;
export function TeamsPage(){
 const current=session.getSnapshot();
 const [teams,setTeams]=useState<Team[]>([]); const [total,setTotal]=useState(0); const [page,setPage]=useState(1); const [detail,setDetail]=useState<Team|null>(null);
 const [busy,setBusy]=useState(false); const [loading,setLoading]=useState(true); const [error,setError]=useState(''); const [notice,setNotice]=useState('');
 const [name,setName]=useState(''); const [editing,setEditing]=useState(false); const [creating,setCreating]=useState(false);
 const [revision,setRevision]=useState(0);
 const canCreateTeam=current?.user.role==='PLAYER';
 async function loadList(){
  setLoading(true);setError('');
  try{const result=await teamsService.list(page);setTeams(result.data);setTotal(result.meta.total);}
  catch(e){setError(errorMessage(e));}finally{setLoading(false);}
 }
 useEffect(()=>{void loadList();},[revision,page]);
 async function openTeam(id:number,preserveNotice=false){
  setLoading(true);setError('');if(!preserveNotice)setNotice('');setCreating(false);setEditing(false);
  try{
   const result=await teamsService.get(id);
   setDetail(result.data);setName(result.data.team_name);
  }catch(e){setError(errorMessage(e));}finally{setLoading(false);}
 }
 async function submitTeam(event:FormEvent<HTMLFormElement>){
  event.preventDefault();const value=name.trim();
  if(value.length<1||value.length>100){setError('Tên đội phải từ 1 đến 100 ký tự.');return;}
  setBusy(true);setError('');setNotice('');
  try{
   if(detail){await teamsService.update(detail.team_id,{team_name:value});setNotice('Đã cập nhật tên đội.');await openTeam(detail.team_id,true);}
   else{const created=await teamsService.create({team_name:value});setNotice('Đã tạo đội mới. Bạn là đội trưởng.');setName('');setCreating(false);setPage(1);setRevision(v=>v+1);await openTeam(created.data.team_id,true);}
  }catch(e){setError(errorMessage(e));}finally{setBusy(false);}
 }
 // The shared AppShell (App.tsx) provides navigation, the top bar and the mobile tab bar.
 return <>
   <div className="account-eyebrow">QUẢN LÝ ĐỘI BÓNG</div><div className="account-page-heading"><div><h1>Đội bóng của tôi<span>.</span></h1><p>Đội là tên để đi tìm đối. Bạn là người đại diện; số người đi đá khai báo mỗi lần gửi yêu cầu.</p></div>{canCreateTeam&&<button className="account-primary-button" onClick={()=>{setDetail(null);setName('');setCreating(v=>!v);setError('');}}>＋ Tạo đội</button>}</div>
    {error&&<div className="notice-error" role="alert">{error}</div>}{notice&&<div className="notice-success" role="status">{notice}</div>}
    {creating&&canCreateTeam&&<section className="profile-form-card"><div className="profile-form-heading"><div><h2>Tạo đội bóng mới</h2><p>Bạn sẽ trở thành đội trưởng đội vừa tạo.</p></div></div><form className="profile-form" onSubmit={submitTeam}><div className="form-field"><label htmlFor="team-name">Tên đội bóng</label><input id="team-name" value={name} maxLength={100} onChange={e=>setName(e.target.value)} placeholder="Ví dụ: FC Chiều Thứ Bảy" required/></div><div className="profile-actions"><button className="account-secondary-button" type="button" onClick={()=>setCreating(false)}>Hủy</button><button className="account-primary-button" disabled={busy}>{busy?'Đang lưu…':'Tạo đội'}</button></div></form></section>}
    <div className="team-workspace">
     <section className="account-panel"><div className="account-section-heading"><div><h2>Danh sách đội bóng</h2><p>{total} đội trong tài khoản</p></div><button className="account-secondary-button" onClick={()=>void loadList()} disabled={loading}>Làm mới</button></div>
      {loading&&!detail?<div className="account-loading">Đang tải đội bóng…</div>:teams.length===0?<div className="mm-empty"><h3>Bạn chưa có đội bóng</h3><p>Tạo đội đầu tiên để tìm đối. Muốn đá cùng đội khác, hãy gửi yêu cầu đá ké ở trang Tìm kèo.</p></div>:<div className="team-manager-list">{teams.map((team,index)=><button key={team.team_id} className={detail?.team_id===team.team_id?'team-manager-item active':'team-manager-item'} onClick={()=>void openTeam(team.team_id)}><span className={'team-manager-crest crest-'+(index%3)}>{team.team_name.split(' ').slice(0,2).map(x=>x[0]).join('').toUpperCase()}</span><span><strong>{team.team_name}</strong><small>{headCount(team)}</small></span><span className="team-manager-status">{team.status==='ACTIVE'?'Hoạt động':'Ngừng'}</span></button>)}</div>}
      {total>20&&<div className="pagination"><button className="small-button" disabled={loading||page<=1} onClick={()=>setPage(value=>value-1)}>← Trước</button><span>Trang {page} / {Math.ceil(total/20)}</span><button className="small-button" disabled={loading||page*20>=total} onClick={()=>setPage(value=>value+1)}>Sau →</button></div>}
     </section>
     <section className="account-panel team-detail-panel">
      {!detail?<div className="mm-empty"><span>⚽</span><h3>Chọn một đội để xem chi tiết</h3><p>Tên đội và số người đi đá lần gần nhất hiển thị tại đây.</p></div>:<>
       <div className="account-section-heading"><div><span className="mm-type">CHI TIẾT ĐỘI BÓNG</span><h2>{detail.team_name}</h2><p>{headCount(detail)}</p></div><button className="account-secondary-button" onClick={()=>setEditing(v=>!v)}>Đổi tên</button></div>
       {editing&&<form className="team-inline-edit" onSubmit={submitTeam}><input value={name} onChange={e=>setName(e.target.value)} maxLength={100} aria-label="Tên đội mới"/><button className="account-primary-button" disabled={busy}>Lưu</button></form>}
       <p className="input-caption">Không cần thêm thành viên. Khi tìm đối, bạn nhập số người đi đá (cả bạn); hệ thống điền sẵn số của lần trước.</p>
      </>}
     </section>
    </div>
 </>;
}
