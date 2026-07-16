import {
    Body,
    Controller,
    Get,
    Post,
} from '@nestjs/common';

import { CreateTicketDto } from './dto/create-ticket.dto';
import { TicketsService } from './tickets.service';

@Controller('tickets')
export class TicketsController {
    constructor(
        private readonly ticketsService: TicketsService,
    ) {}

    @Post()
    create(
        @Body() input: CreateTicketDto,
    ) {
        return this.ticketsService.create(input);
    }

    @Get()
    findAll() {
        return this.ticketsService.findAll();
    }
}