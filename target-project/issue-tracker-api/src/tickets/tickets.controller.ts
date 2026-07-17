import {
  Body,
  Controller,
  Get,
  Post,
  Query,
  Delete,
  Param,
  ParseIntPipe,
  HttpCode,
} from '@nestjs/common';

import { CreateTicketDto } from './dto/create-ticket.dto';
import { TicketsService } from './tickets.service';
import { FindTicketsDto } from './dto/find-tickets.dto';

@Controller('tickets')
export class TicketsController {
  constructor(private readonly ticketsService: TicketsService) {}

  @Post()
  create(@Body() input: CreateTicketDto) {
    return this.ticketsService.create(input);
  }

  @Get()
  findAll(@Query() query: FindTicketsDto) {
    return this.ticketsService.findAll(query);
  }

  @Get(':id')
  async findOne(@Param('id', ParseIntPipe) id: number) {
    return this.ticketsService.findOne(id);
  }

  @Delete(':id')
  @HttpCode(204)
  delete(@Param('id', ParseIntPipe) id: number) {
    return this.ticketsService.delete(id);
  }
}
