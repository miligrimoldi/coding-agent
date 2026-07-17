import { IsOptional, IsString, MinLength, MaxLength } from 'class-validator';

export class CreateTicketDto {
  @IsString()
  @MinLength(3)
  @MaxLength(120)
  title: string;

  @IsOptional()
  @IsString()
  description?: string;
}
