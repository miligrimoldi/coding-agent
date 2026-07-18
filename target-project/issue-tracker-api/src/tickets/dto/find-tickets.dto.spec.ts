import { validate } from 'class-validator';
import { FindTicketsDto } from './find-tickets.dto';
import { TicketStatus } from '../../generated/prisma/client';

describe('FindTicketsDto', () => {
  it('accepts status OPEN', async () => {
    const dto = new FindTicketsDto();
    dto.status = TicketStatus.OPEN;
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('allows omitting status since it is optional', async () => {
    const dto = new FindTicketsDto();
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('rejects invalid status with isEnum', async () => {
    const dto = new FindTicketsDto();
    (dto as unknown as { status: string }).status = 'INVALID_STATUS';
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const statusError = errors.find((e) => e.property === 'status');
    expect(statusError).toBeDefined();
    expect(statusError?.constraints?.isEnum).toBeDefined();
  });
});
