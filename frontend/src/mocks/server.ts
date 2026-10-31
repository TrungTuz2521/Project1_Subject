import { demoUser, initialTeams, pitches, createFixtures } from './fixtures';
import type { Transport } from '../services/api';
import type {
  RegisterRequest, SkillLevel, Team, UserSelf, ProposalDetail, Match, MatchPost,
  TeamMember, Participant, PostCreate, PostType, PostStatus, Notification,
} from '../types/api';

export type MockScenario = 'normal' | 'empty' | 'server-error' | 'network-error' | 'validation-error';
type MockAccount = { user: UserSelf; password: string };
const skillLevels: SkillLevel[] = ['BEGINNER', 'AMATEUR', 'INTERMEDIATE', 'SEMI_PRO', 'PRO'];
const postTypes: PostType[] = ['FIND_OPPONENT', 'RECRUIT_MEMBERS', 'LOOK_FOR_TEAM', 'RANDOM_SQUAD'];
const postStatuses: PostStatus[] = ['OPEN', 'LOCKED', 'MATCHED', 'EXPIRED', 'CANCELLED', 'PENDING_DEPOSIT'];
const iso = (value: unknown): value is string => typeof value === 'string' && Number.isFinite(Date.parse(value));
const paginate = <T,>(items: T[], url: URL, fallback = 20) => {
  const page = Number(url.searchParams.get('page') ?? 1);
  const size = Number(url.searchParams.get('page_size') ?? fallback);
  if (!Number.isInteger(page) || page < 1 || !Number.isInteger(size) || size < 1 || size > 100) return null;
  return { data: items.slice((page - 1) * size, page * size), page, page_size: size, total: items.length };
};

/** In-memory development mock only. It never processes payment or confirms a real booking. */
export function createMockServer(delayMs = 80) {
  let teams = structuredClone(initialTeams);
  let teamMembers: Record<number, TeamMember[]> = {
    1: [
      { user_id: 2, full_name: demoUser.full_name, role: 'CAPTAIN', status: 'ACTIVE', joined_at: new Date().toISOString() },
      ...[4,5,6,7,8,9].map(id => ({ user_id: id, full_name: 'Cầu thủ ' + id, role: 'MEMBER' as const, status: 'ACTIVE' as const, joined_at: new Date().toISOString() })),
    ],
    2: [
      { user_id: 3, full_name: 'Đội trưởng mẫu', role: 'CAPTAIN', status: 'ACTIVE', joined_at: new Date().toISOString() },
      { user_id: 2, full_name: demoUser.full_name, role: 'MEMBER', status: 'ACTIVE', joined_at: new Date().toISOString() },
      ...[5,6,7].map(id => ({ user_id: id, full_name: 'Thành viên ' + id, role: 'MEMBER' as const, status: 'ACTIVE' as const, joined_at: new Date().toISOString() })),
    ],
    3: [
      { user_id: 2, full_name: demoUser.full_name, role: 'CAPTAIN', status: 'ACTIVE', joined_at: new Date().toISOString() },
      ...[10,11,12].map(id => ({ user_id: id, full_name: 'Cầu thủ ghép ' + id, role: 'MEMBER' as const, status: 'ACTIVE' as const, joined_at: new Date().toISOString() })),
    ],
  };
  let nextTeamId = 4;
  let nextUserId = 20;
  let nextPostId = 5;
  let nextParticipantId = 1;
  let nextProposalId = 12;
  let nextMatchId = 1;
  let validToken: string | null = null;
  let tokenDeadline = 0;
  const tokenSessions = new Map<string, { user: UserSelf; expiresAt: number }>();
  let loginCount = 0;
  let currentUser: UserSelf = { ...demoUser };
  let scenario: MockScenario = 'normal';
  const accounts = new Map<string, MockAccount>();
  const seedAccounts = () => {
    accounts.clear();
    accounts.set(demoUser.email, { user: { ...demoUser }, password: 'mock-only' });
    const captain: UserSelf = { user_id: 3, full_name: 'Đội trưởng mẫu', email: 'captain@example.test',
      phone: null, role: 'PLAYER', skill_level: 'INTERMEDIATE', status: 'ACTIVE' };
    accounts.set(captain.email, { user: captain, password: 'mock-only' });
  };
  seedAccounts();
  const fixtures = createFixtures();
  let posts: MatchPost[] = structuredClone(fixtures.posts);
  let proposals: ProposalDetail[] = [structuredClone(fixtures.proposal)];
  let matches: Match[] = [];
  let participants: Participant[] = [];
  let notifications: Notification[] = structuredClone(fixtures.notifications);
  const postOwners = new Map<number, number>([[1,2],[2,3],[3,20],[4,2]]);
  const reply = (data: unknown, status = 200, meta: Record<string, unknown> = {}) => new Response(JSON.stringify({
    data, meta: { server_time: new Date().toISOString(), ...meta },
  }), { status, headers: { 'Content-Type': 'application/json' } });
  const fail = (status: number, code: string, message: string, fields: Record<string, string | string[]> = {}) => new Response(JSON.stringify({
    error: { code, message, ...(Object.keys(fields).length ? { fields } : {}) },
  }), { status, headers: { 'Content-Type': 'application/json' } });
  const parseBody = (init?: RequestInit): Record<string, unknown> | null => {
    try {
      const body: unknown = JSON.parse(String(init?.body ?? ''));
      return body && typeof body === 'object' && !Array.isArray(body) ? body as Record<string, unknown> : null;
    } catch { return null; }
  };
  const currentIsCaptain = (teamId: number) => (teamMembers[teamId] ?? []).some(member =>
    member.user_id === currentUser.user_id && member.role === 'CAPTAIN' && member.status === 'ACTIVE');
  const ownedTeamIds = () => teams.filter(team => (teamMembers[team.team_id] ?? []).some(member =>
    member.user_id === currentUser.user_id && member.status === 'ACTIVE')).map(team => team.team_id);
  const pushNotification = (value: Omit<Notification, 'notification_id' | 'is_read' | 'read_at' | 'created_at'>) => {
    notifications.unshift({ ...value, notification_id: Math.max(0, ...notifications.map(n => n.notification_id)) + 1,
      is_read: false, read_at: null, created_at: new Date().toISOString() });
  };
  const createTeamProposal = (post: MatchPost, participant: Participant, captainId: number) => {
    const expiresAt = Math.min(Date.now() + 15 * 60000, Date.parse(post.expiry_time), post.match_time ? Date.parse(post.match_time) : Infinity);
    const proposal: ProposalDetail = {
      proposal_id: nextProposalId++, source_post_id: post.post_id, target_post_id: null,
      candidate_user_id: participant.user_id, proposal_type: 'TEAM_MEMBER', compatibility_score: '90.00',
      status: 'PENDING_CONFIRMATION', expires_at: new Date(expiresAt).toISOString(), confirmed_at: null,
      confirmations: [
        { user_id: captainId, decision: 'PENDING', responded_at: null },
        { user_id: participant.user_id, decision: 'PENDING', responded_at: null },
      ],
    };
    proposals.unshift(proposal);
    return proposal;
  };

  const transport: Transport = async (input, init) => {
    await new Promise<void>((resolve, reject) => {
      const signal = init?.signal;
      const timer = setTimeout(() => { signal?.removeEventListener('abort', aborted); resolve(); }, delayMs);
      const aborted = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
      if (signal?.aborted) aborted(); else signal?.addEventListener('abort', aborted, { once: true });
    });
    const url = new URL(String(input), 'http://mock.local');
    const path = url.pathname.replace(/^\/api\/v1/, '');
    const parts = path.split('/').filter(Boolean);
    const method = init?.method ?? 'GET';
    const isPublicPostGet = path === '/match-posts' || (parts[0] === 'match-posts' && parts.length === 2 && parts[1] !== 'my' && method === 'GET');
    const publicPath = path === '/auth/login' || path === '/auth/register' || path === '/pitches' || isPublicPostGet;

    if (path === '/auth/register' && method === 'POST') {
      const body = parseBody(init) as Partial<RegisterRequest> | null;
      if (!body) return fail(422, 'VALIDATION_ERROR', 'Dữ liệu đăng ký không hợp lệ.');
      const fullName = typeof body.full_name === 'string' ? body.full_name.trim() : '';
      const email = typeof body.email === 'string' ? body.email.trim().toLocaleLowerCase() : '';
      const password = typeof body.password === 'string' ? body.password : '';
      const passwordBytes = new TextEncoder().encode(password).length;
      const fields: Record<string, string> = {};
      if (fullName.length < 2 || fullName.length > 100) fields.full_name = 'Họ tên phải từ 2 đến 100 ký tự.';
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) fields.email = 'Email không hợp lệ.';
      if (passwordBytes < 8 || passwordBytes > 72) fields.password = 'Mật khẩu phải dài từ 8 đến 72 byte UTF-8.';
      if (body.phone !== undefined && body.phone !== '' && (typeof body.phone !== 'string' || body.phone.trim().length > 30)) fields.phone = 'Số điện thoại không hợp lệ.';
      if (body.skill_level !== undefined && !skillLevels.includes(body.skill_level as SkillLevel)) fields.skill_level = 'Trình độ không hợp lệ.';
      if (Object.keys(fields).length) return fail(422, 'VALIDATION_ERROR', 'Vui lòng kiểm tra lại thông tin đăng ký.', fields);
      if (accounts.has(email)) return fail(409, 'EMAIL_ALREADY_EXISTS', 'Email đã được sử dụng.', { email: 'Email này đã có tài khoản.' });
      const user: UserSelf = {
        user_id: nextUserId++, full_name: fullName, email,
        phone: typeof body.phone === 'string' && body.phone.trim() ? body.phone.trim() : null,
        role: 'PLAYER', skill_level: (body.skill_level as SkillLevel | undefined) ?? 'INTERMEDIATE', status: 'ACTIVE',
      };
      accounts.set(email, { user, password });
      return reply(user, 201);
    }

    if (path === '/auth/login' && method === 'POST') {
      const body = parseBody(init);
      const email = typeof body?.email === 'string' ? body.email.trim().toLocaleLowerCase() : '';
      const password = typeof body?.password === 'string' ? body.password : '';
      const account = accounts.get(email);
      if (!account || account.password !== password || account.user.status !== 'ACTIVE') {
        return fail(401, 'INVALID_CREDENTIALS', 'Email hoặc mật khẩu không chính xác.');
      }
      validToken = 'mock-session-' + (++loginCount);
      tokenDeadline = Date.now() + 3600000;
      currentUser = { ...account.user };
      tokenSessions.set(validToken, { user: { ...currentUser }, expiresAt: tokenDeadline });
      return reply({ access_token: validToken, expires_in: 3600, user: currentUser });
    }

    const authorization = new Headers(init?.headers).get('Authorization');
    const requestToken = authorization?.startsWith('Bearer ') ? authorization.slice(7) : null;
    const tokenSession = requestToken ? tokenSessions.get(requestToken) : undefined;
    if (!publicPath && (!tokenSession || Date.now() >= tokenSession.expiresAt)) {
      return fail(401, 'TOKEN_EXPIRED', 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.');
    }
    if (tokenSession) currentUser = { ...tokenSession.user };
    if (scenario === 'network-error') throw new TypeError('Simulated offline');
    if (scenario === 'server-error') return fail(500, 'INTERNAL_ERROR', 'Không tải được dữ liệu mẫu. Hãy chọn chế độ bình thường rồi thử lại.');

    if (path === '/users/me' && method === 'GET') return reply(currentUser);
    if (path === '/users/me' && method === 'PATCH') {
      const body = parseBody(init);
      if (!body) return fail(422, 'VALIDATION_ERROR', 'Dữ liệu hồ sơ không hợp lệ.');
      const fields: Record<string, string> = {};
      if (body.full_name !== undefined && (typeof body.full_name !== 'string' || body.full_name.trim().length < 2 || body.full_name.trim().length > 100)) fields.full_name = 'Họ tên phải từ 2 đến 100 ký tự.';
      if (body.phone !== undefined && body.phone !== null && (typeof body.phone !== 'string' || body.phone.trim().length > 30)) fields.phone = 'Số điện thoại không hợp lệ.';
      if (body.skill_level !== undefined && !skillLevels.includes(body.skill_level as SkillLevel)) fields.skill_level = 'Trình độ không hợp lệ.';
      if (Object.keys(fields).length) return fail(422, 'VALIDATION_ERROR', 'Vui lòng kiểm tra lại hồ sơ.', fields);
      currentUser = { ...currentUser,
        ...(typeof body.full_name === 'string' ? { full_name: body.full_name.trim() } : {}),
        ...(body.phone !== undefined ? { phone: typeof body.phone === 'string' && body.phone.trim() ? body.phone.trim() : null } : {}),
        ...(typeof body.skill_level === 'string' ? { skill_level: body.skill_level as SkillLevel } : {}),
      };
      const account = accounts.get(currentUser.email);
      if (account) accounts.set(currentUser.email, { ...account, user: { ...currentUser } });
      return reply(currentUser);
    }

    if (path === '/teams' && method === 'GET') {
      const visible = scenario === 'empty' ? [] : teams.filter(team => ownedTeamIds().includes(team.team_id));
      const result = paginate(visible, url);
      return result ? reply(result.data, 200, { page: result.page, page_size: result.page_size, total: result.total }) : fail(422, 'VALIDATION_ERROR', 'Phân trang không hợp lệ.');
    }
    if (path === '/teams' && method === 'POST') {
      const body = parseBody(init);const name = body?.team_name;
      if (typeof name !== 'string' || !name.trim() || name.trim().length > 100 || scenario === 'validation-error') return fail(422, 'VALIDATION_ERROR', 'Kiểm tra lại thông tin đội bóng.', { team_name: 'Tên đội cần từ 1 đến 100 ký tự.' });
      if (teams.some(team => team.team_name.toLocaleLowerCase() === name.trim().toLocaleLowerCase())) return fail(409, 'STATE_CONFLICT', 'Đã có đội dùng tên này.', { team_name: 'Hãy chọn một tên khác.' });
      const team: Team = { team_id: nextTeamId++, team_name: name.trim(), created_by: currentUser.user_id, creation_type: 'USER_CREATED', status: 'ACTIVE', active_member_count: 1 };
      teams.unshift(team);
      teamMembers[team.team_id] = [{ user_id: currentUser.user_id, full_name: currentUser.full_name, role: 'CAPTAIN', status: 'ACTIVE', joined_at: new Date().toISOString() }];
      return reply(team, 201);
    }
    if (parts[0] === 'teams' && parts.length === 2 && method === 'GET') {
      const teamId = Number(parts[1]);const team = teams.find(t => t.team_id === teamId);
      if (!team) return fail(404, 'NOT_FOUND', 'Không tìm thấy đội bóng.');
      if (currentUser.role !== 'ADMIN' && !ownedTeamIds().includes(teamId)) return fail(403, 'FORBIDDEN', 'Bạn không phải thành viên của đội.');
      return reply({ ...team, members: teamMembers[teamId] ?? [] });
    }
    if (parts[0] === 'teams' && parts.length === 2 && method === 'PATCH') {
      const teamId=Number(parts[1]);const team=teams.find(t=>t.team_id===teamId);
      if(!team)return fail(404,'NOT_FOUND','Không tìm thấy đội bóng.');
      if(!currentIsCaptain(teamId))return fail(403,'FORBIDDEN','Chỉ đội trưởng mới được sửa thông tin đội.');
      const name=parseBody(init)?.team_name;
      if(typeof name!=='string'||name.trim().length<1||name.trim().length>100)return fail(422,'VALIDATION_ERROR','Tên đội không hợp lệ.',{team_name:'Tên đội cần từ 1 đến 100 ký tự.'});
      team.team_name=name.trim();return reply(team);
    }
    if(parts[0]==='teams'&&parts[2]==='join-requests'&&parts.length===3&&method==='POST'){
      const teamId=Number(parts[1]);const team=teams.find(t=>t.team_id===teamId);
      if(!team)return fail(404,'NOT_FOUND','Không tìm thấy đội bóng.');
      if((teamMembers[teamId]??[]).some(m=>m.user_id===currentUser.user_id&&m.status==='ACTIVE'))return fail(409,'ALREADY_MEMBER','Bạn đã là thành viên đội này.');
      const recruitPosts=posts.filter(p=>p.team_id===teamId&&p.post_type==='RECRUIT_MEMBERS'&&p.status==='OPEN');
      if(recruitPosts.length===0)return fail(409,'RECRUITMENT_NOT_OPEN','Đội hiện không mở tuyển thành viên.');
      if(recruitPosts.length>1)return fail(409,'STATE_CONFLICT','Đội có nhiều bài tuyển đang mở; hãy đăng ký trực tiếp từ bài cụ thể.');
      const post=recruitPosts[0];
      const existing=participants.find(p=>p.post_id===post.post_id&&p.user_id===currentUser.user_id&&p.status==='PENDING');
      if(existing)return fail(409,'STATE_CONFLICT','Bạn đã gửi yêu cầu tham gia.');
      const participant:Participant={participant_id:nextParticipantId++,post_id:post.post_id,user_id:currentUser.user_id,status:'PENDING',joined_at:new Date().toISOString()};
      participants.push(participant);
      const proposal=createTeamProposal(post,participant,team.created_by??0);
      pushNotification({notification_type:'TEAM_JOINED',title:'Có yêu cầu tham gia đội',content:'Một người chơi đã gửi yêu cầu tham gia đội '+team.team_name+'.',proposal_id:proposal.proposal_id,match_id:null});
      return reply({ ...participant, proposal_id: proposal.proposal_id },201);
    }
    if(parts[0]==='teams'&&parts[2]==='join-requests'&&parts[4]==='respond'&&parts.length===5&&method==='PATCH'){
      const teamId=Number(parts[1]);const postId=Number(parts[3]);
      if(!currentIsCaptain(teamId))return fail(403,'FORBIDDEN','Chỉ đội trưởng mới được xử lý yêu cầu.');
      const decision=parseBody(init)?.decision;
      if(decision!=='ACCEPTED'&&decision!=='DECLINED')return fail(422,'VALIDATION_ERROR','Quyết định không hợp lệ.');
      const participant=participants.find(p=>p.post_id===postId&&p.status==='PENDING');
      if(!participant)return fail(404,'NOT_FOUND','Không có yêu cầu đang chờ.');
      participant.status=decision==='ACCEPTED'?'ACCEPTED':'REJECTED';
      const proposal=proposals.find(p=>p.proposal_type==='TEAM_MEMBER'&&p.source_post_id===postId&&p.candidate_user_id===participant.user_id);
      if(proposal){const captainConfirmation=proposal.confirmations.find(c=>c.user_id===currentUser.user_id);if(captainConfirmation){captainConfirmation.decision=decision;captainConfirmation.responded_at=new Date().toISOString();if(decision==='DECLINED')proposal.status='REJECTED';}}
      return reply({ ...participant, proposal_id: proposal?.proposal_id ?? 0 });
    }
    if(parts[0]==='teams'&&parts[2]==='members'&&parts[3]==='me'&&method==='DELETE'){
      const teamId=Number(parts[1]);if(currentIsCaptain(teamId))return fail(409,'CAPTAIN_TRANSFER_REQUIRED','Đội trưởng cần chuyển quyền trước khi rời đội.');
      const member=(teamMembers[teamId]??[]).find(m=>m.user_id===currentUser.user_id&&m.status==='ACTIVE');
      if(!member)return fail(404,'NOT_FOUND','Bạn không phải thành viên đang hoạt động.');
      member.status='LEFT';const team=teams.find(t=>t.team_id===teamId);if(team)team.active_member_count=Math.max(0,team.active_member_count-1);
      return reply({team_id:teamId,status:'LEFT'});
    }
    if(parts[0]==='teams'&&parts[2]==='members'&&parts.length===4&&method==='DELETE'){
      const teamId=Number(parts[1]);const userId=Number(parts[3]);
      if(!currentIsCaptain(teamId))return fail(403,'FORBIDDEN','Chỉ đội trưởng mới được xóa thành viên.');
      const member=(teamMembers[teamId]??[]).find(m=>m.user_id===userId&&m.status==='ACTIVE');
      if(!member)return fail(404,'NOT_FOUND','Không tìm thấy thành viên đang hoạt động.');
      if(member.role==='CAPTAIN')return fail(409,'CAPTAIN_TRANSFER_REQUIRED','Không thể xóa đội trưởng.');
      member.status='REMOVED';const team=teams.find(t=>t.team_id===teamId);if(team)team.active_member_count=Math.max(0,team.active_member_count-1);
      return reply({team_id:teamId,user_id:userId,status:'REMOVED'});
    }

    if(path==='/pitches'&&method==='GET')return reply(pitches,200,{page:1,page_size:20,total:pitches.length});
    if(path==='/match-posts'&&method==='GET'){
      let visible=[...posts];
      const type=url.searchParams.get('post_type');const pitch=url.searchParams.get('pitch_type');const skill=url.searchParams.get('skill_level');
      const from=url.searchParams.get('from');const to=url.searchParams.get('to');
      if(type)visible=visible.filter(p=>p.post_type===type);if(pitch)visible=visible.filter(p=>p.pitch_type===pitch);if(skill)visible=visible.filter(p=>p.skill_level===skill);
      if(from)visible=visible.filter(p=>p.match_time&&Date.parse(p.match_time)>=Date.parse(from));if(to)visible=visible.filter(p=>p.match_time&&Date.parse(p.match_time)<=Date.parse(to));
      const result=paginate(visible,url);return result?reply(result.data,200,{page:result.page,page_size:result.page_size,total:result.total}):fail(422,'VALIDATION_ERROR','Phân trang không hợp lệ.');
    }
    if(path==='/match-posts/my'&&method==='GET'){
      let mine=posts.filter(p=>postOwners.get(p.post_id)===currentUser.user_id);
      const status=url.searchParams.get('status');if(status)mine=mine.filter(p=>p.status===status);
      const result=paginate(mine,url);return result?reply(result.data,200,{page:result.page,page_size:result.page_size,total:result.total}):fail(422,'VALIDATION_ERROR','Phân trang không hợp lệ.');
    }
    if(path==='/match-posts'&&method==='POST'){
      const body=parseBody(init) as Partial<PostCreate>|null;if(!body)return fail(422,'VALIDATION_ERROR','Dữ liệu bài đăng không hợp lệ.');
      const fields:Record<string,string>={};
      if(typeof body.title!=='string'||body.title.trim().length<1||body.title.trim().length>150)fields.title='Tiêu đề cần từ 1 đến 150 ký tự.';
      if(!body.post_type||!postTypes.includes(body.post_type))fields.post_type='Loại bài đăng không hợp lệ.';
      if(!body.skill_level||!skillLevels.includes(body.skill_level))fields.skill_level='Trình độ không hợp lệ.';
      if(!iso(body.expiry_time)||Date.parse(body.expiry_time)<=Date.now())fields.expiry_time='Hạn bài phải nằm trong tương lai.';
      const needsSlot=body.post_type!=='LOOK_FOR_TEAM';
      if(body.post_type!=='LOOK_FOR_TEAM'&&!Number.isInteger(body.team_id))fields.team_id='Chọn đội bóng.';
      if(needsSlot&&(!iso(body.match_time)||!iso(body.end_time)||Date.parse(body.end_time as string)-Date.parse(body.match_time as string)!==90*60000))fields.match_time='Khung giờ phải đủ 90 phút.';
      if(body.post_type!=='LOOK_FOR_TEAM'&&(!body.pitch_type||!['PITCH_5','PITCH_7'].includes(body.pitch_type)))fields.pitch_type='Chọn loại sân 5 hoặc sân 7.';
      if(body.post_type==='FIND_OPPONENT'||body.post_type==='RECRUIT_MEMBERS'){if(!body.payment_rule)fields.payment_rule='Chọn quy tắc thanh toán.';}
      if(body.post_type==='RECRUIT_MEMBERS'||body.post_type==='RANDOM_SQUAD'){if(!Number.isInteger(body.required_players)||Number(body.required_players)<1)fields.required_players='Số người cần tuyển không hợp lệ.';}
      if(body.description!==undefined&&(typeof body.description!=='string'||body.description.length>3000))fields.description='Mô tả tối đa 3000 ký tự.';
      if(Object.keys(fields).length||scenario==='validation-error')return fail(422,'VALIDATION_ERROR','Kiểm tra lại bài đăng.',fields);
      const teamId=body.team_id??null;
      if(teamId!==null&&!currentIsCaptain(teamId))return fail(403,'FORBIDDEN','Chỉ đội trưởng mới được đăng bài cho đội.');
      const post:MatchPost={post_id:nextPostId++,title:(body.title as string).trim(),description:body.description??null,post_type:body.post_type as PostType,
        team_id:teamId,pitch_id:body.pitch_id??null,pitch_type:body.pitch_type??null,match_time:body.match_time??null,end_time:body.end_time??null,
        skill_level:body.skill_level as SkillLevel,payment_rule:body.payment_rule??null,required_players:body.required_players??null,
        current_players:teamId?(teams.find(t=>t.team_id===teamId)?.active_member_count??1):1,expiry_time:body.expiry_time as string,status:'OPEN',
        matching_ready:needsSlot};
      posts.unshift(post);postOwners.set(post.post_id,currentUser.user_id);return reply(post,201);
    }
    if(parts[0]==='match-posts'&&parts.length===2&&method==='GET'){
      const post=posts.find(p=>p.post_id===Number(parts[1]));return post?reply(post):fail(404,'NOT_FOUND','Không tìm thấy bài đăng.');
    }
    if(parts[0]==='match-posts'&&parts[2]==='participants'&&parts.length===3&&method==='GET'){
      const post=posts.find(p=>p.post_id===Number(parts[1]));if(!post)return fail(404,'NOT_FOUND','Không tìm thấy bài đăng.');
      if(postOwners.get(post.post_id)!==currentUser.user_id&&currentUser.role!=='ADMIN'&&!(post.team_id&&currentIsCaptain(post.team_id)))return fail(403,'FORBIDDEN','Bạn không có quyền xem người đăng ký.');
      const rows=participants.filter(p=>p.post_id===post.post_id);const result=paginate(rows,url);return result?reply(result.data,200,{page:result.page,page_size:result.page_size,total:result.total}):fail(422,'VALIDATION_ERROR','Phân trang không hợp lệ.');
    }
    if(parts[0]==='match-posts'&&parts[2]==='participants'&&parts.length===3&&method==='POST'){
      const post=posts.find(p=>p.post_id===Number(parts[1]));if(!post)return fail(404,'NOT_FOUND','Không tìm thấy bài đăng.');
      if(post.status!=='OPEN')return fail(409,'STATE_CONFLICT','Bài đăng không còn mở.');
      if(postOwners.get(post.post_id)===currentUser.user_id)return fail(409,'STATE_CONFLICT','Không thể tự đăng ký bài của mình.');
      const existing=participants.find(p=>p.post_id===post.post_id&&p.user_id===currentUser.user_id&&p.status==='PENDING');
      if(existing)return fail(409,'STATE_CONFLICT','Bạn đã gửi yêu cầu.');
      const participant:Participant={participant_id:nextParticipantId++,post_id:post.post_id,user_id:currentUser.user_id,status:'PENDING',joined_at:new Date().toISOString()};
      participants.push(participant);
      const ownerId=postOwners.get(post.post_id)??(post.team_id?teams.find(t=>t.team_id===post.team_id)?.created_by:0)??0;
      const proposal=createTeamProposal(post,participant,ownerId);
      pushNotification({notification_type:'MATCH_PROPOSAL',title:'Yêu cầu của bạn đã được gửi',content:'Đang chờ bên còn lại xác nhận.',proposal_id:proposal.proposal_id,match_id:null});
      return reply({...participant,proposal_id:proposal.proposal_id},201);
    }
    if(parts[0]==='match-posts'&&parts.length===2&&method==='PATCH'){
      const post=posts.find(p=>p.post_id===Number(parts[1]));if(!post)return fail(404,'NOT_FOUND','Không tìm thấy bài đăng.');
      if(postOwners.get(post.post_id)!==currentUser.user_id)return fail(403,'FORBIDDEN','Bạn không phải chủ bài.');
      if(post.status!=='OPEN')return fail(409,'STATE_CONFLICT','Chỉ sửa bài đang mở.');
      if(proposals.some(p=>(p.source_post_id===post.post_id||p.target_post_id===post.post_id)&&p.status==='PENDING_CONFIRMATION'))return fail(409,'STATE_CONFLICT','Bài đang có đề xuất ghép.');
      const body=parseBody(init)??{};
      if(body.title!==undefined){if(typeof body.title!=='string'||body.title.trim().length<1||body.title.trim().length>150)return fail(422,'VALIDATION_ERROR','Tiêu đề không hợp lệ.',{title:'Từ 1 đến 150 ký tự.'});post.title=body.title.trim();}
      if(body.description!==undefined){if(typeof body.description!=='string'||body.description.length>3000)return fail(422,'VALIDATION_ERROR','Mô tả không hợp lệ.',{description:'Tối đa 3000 ký tự.'});post.description=body.description;}
      return reply(post);
    }
    if(parts[0]==='match-posts'&&parts[2]==='cancel'&&parts.length===3&&method==='POST'){
      const post=posts.find(p=>p.post_id===Number(parts[1]));if(!post)return fail(404,'NOT_FOUND','Không tìm thấy bài đăng.');
      if(postOwners.get(post.post_id)!==currentUser.user_id)return fail(403,'FORBIDDEN','Bạn không phải chủ bài.');
      if(post.status!=='OPEN')return fail(409,'STATE_CONFLICT','Bài đăng không ở trạng thái có thể hủy.');
      if(proposals.some(p=>(p.source_post_id===post.post_id||p.target_post_id===post.post_id)&&p.status==='PENDING_CONFIRMATION'))return fail(409,'STATE_CONFLICT','Bài đang có đề xuất ghép hoạt động.');
      post.status='CANCELLED';return reply(post);
    }

    if(path==='/match-proposals'&&method==='GET'){
      const result=paginate(proposals,url);return result?reply(result.data,200,{page:result.page,page_size:result.page_size,total:result.total}):fail(422,'VALIDATION_ERROR','Phân trang không hợp lệ.');
    }
    if(parts[0]==='match-proposals'&&parts.length===2&&method==='GET'){
      const proposal=proposals.find(p=>p.proposal_id===Number(parts[1]));return proposal?reply(proposal):fail(404,'NOT_FOUND','Không tìm thấy đề xuất.');
    }
    if(parts[0]==='match-proposals'&&parts[2]==='respond'&&parts.length===3&&method==='POST'){
      const proposal=proposals.find(p=>p.proposal_id===Number(parts[1]));if(!proposal)return fail(404,'NOT_FOUND','Không tìm thấy đề xuất.');
      if(Date.parse(proposal.expires_at)<=Date.now()){proposal.status='EXPIRED';return fail(409,'PROPOSAL_EXPIRED','Đề xuất đã hết hạn.');}
      if(proposal.status!=='PENDING_CONFIRMATION')return fail(409,'ALREADY_RESPONDED','Đề xuất đã được xử lý.');
      const decision=parseBody(init)?.decision;if(decision!=='ACCEPTED'&&decision!=='DECLINED')return fail(422,'VALIDATION_ERROR','Quyết định không hợp lệ.');
      const confirmation=proposal.confirmations.find(item=>item.user_id===currentUser.user_id);if(!confirmation)return fail(403,'FORBIDDEN','Bạn không có quyền phản hồi đề xuất.');
      if(confirmation.decision!=='PENDING')return fail(409,'ALREADY_RESPONDED','Bạn đã phản hồi đề xuất này.');
      confirmation.decision=decision;confirmation.responded_at=new Date().toISOString();
      if(decision==='DECLINED'){
        proposal.status='REJECTED';
        const rejectedParticipant=participants.find(p=>p.post_id===proposal.source_post_id&&p.user_id===proposal.candidate_user_id);
        if(rejectedParticipant)rejectedParticipant.status='REJECTED';
      }
      else if(proposal.confirmations.every(item=>item.decision==='ACCEPTED')){
        proposal.status='ACCEPTED';proposal.confirmed_at=new Date().toISOString();
        if(proposal.proposal_type==='TEAM_MEMBER'&&proposal.candidate_user_id!==null){
          const sourcePost=posts.find(p=>p.post_id===proposal.source_post_id);
          if(sourcePost?.team_id){
            const currentMembers=teamMembers[sourcePost.team_id]??[];
            if(!currentMembers.some(m=>m.user_id===proposal.candidate_user_id&&m.status==='ACTIVE')){
              const candidate=Array.from(accounts.values()).find(a=>a.user.user_id===proposal.candidate_user_id)?.user;
              currentMembers.push({user_id:proposal.candidate_user_id,full_name:candidate?.full_name??('Người chơi #'+proposal.candidate_user_id),role:'MEMBER',status:'ACTIVE',joined_at:new Date().toISOString()});
              teamMembers[sourcePost.team_id]=currentMembers;
              const sourceTeam=teams.find(t=>t.team_id===sourcePost.team_id);if(sourceTeam)sourceTeam.active_member_count=currentMembers.filter(m=>m.status==='ACTIVE').length;
            }
          }
          const acceptedParticipant=participants.find(p=>p.post_id===proposal.source_post_id&&p.user_id===proposal.candidate_user_id);
          if(acceptedParticipant)acceptedParticipant.status='ACCEPTED';
        }
        if(proposal.proposal_type==='OPPONENT'){
          const post=posts.find(p=>p.post_id===proposal.source_post_id);
          const match:Match={match_id:nextMatchId++,post_id:proposal.source_post_id,opponent_post_id:proposal.target_post_id,
            proposal_id:proposal.proposal_id,booking_id:null,match_time:post?.match_time??new Date().toISOString(),status:'SUGGESTED',confirmed_at:null};
          matches.unshift(match);proposal.match_id=match.match_id;
        }
      }
      return reply(proposal);
    }
    if(path==='/matches'&&method==='GET'){
      let visible=[...matches];const status=url.searchParams.get('status');if(status)visible=visible.filter(m=>m.status===status);
      const result=paginate(visible,url);return result?reply(result.data,200,{page:result.page,page_size:result.page_size,total:result.total}):fail(422,'VALIDATION_ERROR','Phân trang không hợp lệ.');
    }
    if(parts[0]==='matches'&&parts.length===2&&method==='GET'){
      const match=matches.find(m=>m.match_id===Number(parts[1]));if(!match)return fail(404,'NOT_FOUND','Không tìm thấy trận.');
      const post=posts.find(p=>p.post_id===match.post_id);const opponentPost=match.opponent_post_id===null?undefined:posts.find(p=>p.post_id===match.opponent_post_id);
      const teamIds=[post?.team_id,opponentPost?.team_id].filter((id):id is number=>id!==null&&id!==undefined);
      const teamList=teams.filter(t=>teamIds.includes(t.team_id));
      const proposal=proposals.find(p=>p.proposal_id===match.proposal_id)??proposals[0];
      return reply({...match,end_time:post?.end_time??match.match_time,proposal,teams:teamList,booking:null,payer_progress:[]});
    }
    if(path==='/notifications'&&method==='GET'){
      let visible=[...notifications];const read=url.searchParams.get('is_read');if(read!==null)visible=visible.filter(n=>String(n.is_read)===read);
      const result=paginate(visible,url);return result?reply(result.data,200,{page:result.page,page_size:result.page_size,total:result.total}):fail(422,'VALIDATION_ERROR','Phân trang không hợp lệ.');
    }
    if(parts[0]==='notifications'&&parts[2]==='read'&&parts.length===3&&method==='PATCH'){
      const notification=notifications.find(n=>n.notification_id===Number(parts[1]));if(!notification)return fail(404,'NOT_FOUND','Không tìm thấy thông báo.');
      notification.is_read=true;notification.read_at=new Date().toISOString();return reply(notification);
    }
    if(path==='/bookings/my'&&method==='GET')return reply([fixtures.booking],200,{page:1,page_size:20,total:1});
    return fail(501,'MOCK_NOT_IMPLEMENTED','Mock chưa hỗ trợ '+method+' '+path+'. Bổ sung handler trước khi dùng.');
  };

  return {
    transport,
    setScenario: (value: MockScenario) => { scenario = value; },
    expireSession: () => { tokenDeadline = 0; if (validToken) tokenSessions.delete(validToken); },
    reset: () => {
      teams=structuredClone(initialTeams);nextTeamId=4;nextUserId=20;nextPostId=5;nextParticipantId=1;nextProposalId=12;nextMatchId=1;
      teamMembers={
        1:[{user_id:2,full_name:demoUser.full_name,role:'CAPTAIN',status:'ACTIVE',joined_at:new Date().toISOString()}],
        2:[{user_id:3,full_name:'Đội trưởng mẫu',role:'CAPTAIN',status:'ACTIVE',joined_at:new Date().toISOString()},{user_id:2,full_name:demoUser.full_name,role:'MEMBER',status:'ACTIVE',joined_at:new Date().toISOString()}],
        3:[{user_id:2,full_name:demoUser.full_name,role:'CAPTAIN',status:'ACTIVE',joined_at:new Date().toISOString()}],
      };
      posts=structuredClone(fixtures.posts);proposals=[structuredClone(fixtures.proposal)];matches=[];participants=[];notifications=structuredClone(fixtures.notifications);
      validToken=null;tokenDeadline=0;tokenSessions.clear();currentUser={...demoUser};scenario='normal';seedAccounts();
    },
  };
}
