import { afterEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
const { request } = vi.hoisted(()=>({request:vi.fn()}));
vi.mock('./client',()=>({api:{request}}));
import { confirmDemoDeposit, getDepositInstructions } from './depositBank';
import { BankDepositBox } from '../features/payments/BankDepositBox';
import type { BankDepositInstructions } from '../types/api';
afterEach(()=>request.mockReset());

it('loads read-only private QR instructions without opening a payment session',async()=>{
  request.mockResolvedValueOnce({data:{booking_id:17},meta:{server_time:new Date().toISOString()}});
  expect(await getDepositInstructions(17)).toEqual({booking_id:17});
  expect(request).toHaveBeenCalledTimes(1);
  expect(request).toHaveBeenLastCalledWith('/bookings/17/deposit-instructions',{signal:undefined});
});

it('shows recipient, own deposit and transfer reference, and explains manual confirmation',()=>{
  const instructions:BankDepositInstructions={demo_payment_enabled:true,booking_id:17,status:'PENDING_HOLD',expires_at:'2030-01-01T12:00:00Z',payment_method:'BANK_TRANSFER',
    bank_bin:'970418',bank_name:'Test Bank',account_no:'123456789',account_name:'TEST RECEIVER',payers:[{
      user_id:2,required_amount:'60000.00',paid_amount:'0.00',status:'UNPAID',due_amount:'60000.00',transfer_reference:'COC17U2',
      qr_payload:null,unavailable_reason:'Test only',can_confirm:true,
    }]};
  const html=renderToStaticMarkup(<BankDepositBox instructions={instructions} validHold demo/>);
  expect(html).toContain('123456789');expect(html).toContain('TEST RECEIVER');expect(html).toContain('COC17U2');
  expect(html).toContain('Xác nhận thanh toán cọc (demo)');expect(html).not.toContain('Admin');expect(html).not.toContain('VNPay');
  const expired=renderToStaticMarkup(<BankDepositBox instructions={instructions} validHold={false} demo/>);
  expect(expired).toContain('Đã hết hạn nhận cọc');expect(expired).toContain('disabled');
});

it('posts only a booking ID for persisted demo confirmation; user and amount are server-owned',async()=>{
  request.mockResolvedValueOnce({data:{demo:true,booking:{booking_id:17},payment:{is_demo:true}},meta:{server_time:new Date().toISOString()}});
  const result=await confirmDemoDeposit(17);
  expect(result.demo).toBe(true);
  expect(request).toHaveBeenCalledWith('/payments/deposit/demo-confirm',{method:'POST',body:{booking_id:17}});
});

it('with SePay on, shows a server-owned 60-second QR with pre-filled amount and content, never a static one',async()=>{
  const now=Date.now();
  const session={payment_id:9,booking_id:17,status:'PENDING' as const,amount:'60000.00',transfer_reference:'SPA1B2C3D4E5',
    qr_payload:'000201010212',qr_expires_at:new Date(now+45_000).toISOString(),hold_expires_at:new Date(now+200_000).toISOString(),
    bank_name:'Test Bank',account_no:'123456789',account_name:'TEST RECEIVER'};
  const base:BankDepositInstructions={qr_auto_confirm:true,qr_ttl_seconds:60,booking_id:17,status:'PENDING_HOLD',expires_at:'2030-01-01T12:00:00Z',payment_method:'BANK_TRANSFER',
    bank_bin:'970418',bank_name:'Test Bank',account_no:'123456789',account_name:'TEST RECEIVER',payers:[{
      user_id:2,required_amount:'60000.00',paid_amount:'0.00',status:'UNPAID',due_amount:'60000.00',transfer_reference:'COC17U2',
      qr_payload:null,unavailable_reason:null,can_confirm:true,can_open_qr:true,qr_session:null}]};
  const idle=renderToStaticMarkup(<BankDepositBox instructions={base} validHold demo={false}/>);
  expect(idle).toContain('Tạo mã QR thanh toán (60 giây)');expect(idle).not.toContain('Chưa tích hợp');
  const live=renderToStaticMarkup(<BankDepositBox instructions={{...base,payers:[{...base.payers[0],qr_session:session}]}} validHold demo={false}/>);
  expect(live).toContain('SPA1B2C3D4E5');expect(live).toContain('đã điền sẵn');expect(live).toContain('Mã QR hết hiệu lực sau');
  const expired=renderToStaticMarkup(<BankDepositBox instructions={{...base,payers:[{...base.payers[0],qr_session:{...session,qr_expires_at:new Date(now-1000).toISOString()}}]}} validHold demo={false}/>);
  expect(expired).toContain('Mã QR đã hết hiệu lực');expect(expired).toContain('Tạo mã QR mới');expect(expired).not.toContain('SPA1B2C3D4E5');
  request.mockResolvedValueOnce({data:session,meta:{server_time:new Date().toISOString()}});
  const { openQrPayment } = await import('./depositBank');
  expect((await openQrPayment(17)).transfer_reference).toBe('SPA1B2C3D4E5');
  expect(request).toHaveBeenCalledWith('/payments/deposit/qr',{method:'POST',body:{booking_id:17}});
});
