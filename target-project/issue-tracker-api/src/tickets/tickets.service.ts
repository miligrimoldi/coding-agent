import { Injectable } from '@nestjs/common';

import { PrismaService } from '../prisma/prisma.service';
import { CreateTicketDto } from './dto/create-ticket.dto';

@Injectable()
export class TicketsService {
    constructor(
        private readonly prisma: PrismaService,
    ) {}

    create(input: CreateTicketDto) {
        return this.prisma.ticket.create({
            data: {
                title: input.title,
                description: input.description,
            },
        });
    }

    findAll() {
        return this.prisma.ticket.findMany({
            orderBy: {
                createdAt: 'desc',
            },
        });
    }
}