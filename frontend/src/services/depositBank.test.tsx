import { afterEach, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
const { request } = vi.hoisted(()=>({request:vi.fn()}));
vi.mock('./client',()=>({useMocks:false,api:{request}}));
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
