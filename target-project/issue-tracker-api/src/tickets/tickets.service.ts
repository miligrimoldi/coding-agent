import { Injectable, NotFoundException } from '@nestjs/common';

import { Prisma } from '../generated/prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { CreateTicketDto } from './dto/create-ticket.dto';
import { FindTicketsDto } from './dto/find-tickets.dto';

@Injectable()
export class TicketsService {
  constructor(private readonly prisma: PrismaService) {}

  create(input: CreateTicketDto) {
    return this.prisma.ticket.create({
      data: {
        title: input.title,
        description: input.description,
      },
    });
  }

  async findAll(findTicketsDto?: FindTicketsDto) {
    const where: Prisma.TicketWhereInput = {};

    if (findTicketsDto?.status !== undefined) {
      where.status = findTicketsDto.status;
    }

    return this.prisma.ticket.findMany({
      where: where.status ? where : undefined,
      orderBy: {
        createdAt: 'desc',
      },
    });
  }

  async findOne(id: number) {
    const ticket = await this.prisma.ticket.findUnique({ where: { id } });
    if (!ticket) {
      throw new NotFoundException(`Ticket with id ${id} not found`);
    }
    return ticket;
  }

  async delete(id: number) {
    // Check existence first to return 404 if not found
    const existing = await this.prisma.ticket.findUnique({ where: { id } });
    if (!existing) {
      throw new NotFoundException(`Ticket with id ${id} not found`);
    }

    // Delete and return nothing (204) or could return deleted object
    await this.prisma.ticket.delete({ where: { id } });
    return;
  }
}
