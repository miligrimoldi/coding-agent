import { IsEnum, IsOptional } from 'class-validator';
import { TicketStatus } from '../../generated/prisma/client';

export class FindTicketsDto {
  @IsOptional()
  @IsEnum(TicketStatus)
  status?: TicketStatus;
}
