import { validate } from 'class-validator';
import { CreateTicketDto } from './create-ticket.dto';

describe('CreateTicketDto', () => {
  it('should accept a valid title with 120 characters', async () => {
    const dto = new CreateTicketDto();
    dto.title = 'a'.repeat(120);
    dto.description = 'desc';

    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should reject a title longer than 120 characters', async () => {
    const dto = new CreateTicketDto();
    dto.title = 'a'.repeat(121);
    dto.description = 'desc';

    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const hasTitleError = errors.some((e) => e.property === 'title');
    expect(hasTitleError).toBeTruthy();
  });
});
