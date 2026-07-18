import { Test } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';

import { PrismaService } from '../prisma/prisma.service';
import { TicketsService } from './tickets.service';
import { FindTicketsDto } from './dto/find-tickets.dto';
import { Ticket, TicketStatus } from '../generated/prisma/client';

describe('TicketsService', () => {
  let service: TicketsService;

  const prismaMock = {
    ticket: {
      create: jest.fn(),
      findMany: jest.fn(),
      findUnique: jest.fn(),
      delete: jest.fn(),
    },
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    const moduleRef = await Test.createTestingModule({
      providers: [
        TicketsService,
        {
          provide: PrismaService,
          useValue: prismaMock,
        },
      ],
    }).compile();

    service = moduleRef.get(TicketsService);
  });

  it('creates a ticket', async () => {
    prismaMock.ticket.create.mockResolvedValue({
      id: 1,
      title: 'Error de login',
      description: null,
      status: 'OPEN',
    });

    await service.create({
      title: 'Error de login',
    });

    expect(prismaMock.ticket.create).toHaveBeenCalledWith({
      data: {
        title: 'Error de login',
        description: undefined,
      },
    });
  });

  it('lists tickets ordered by creation date', async () => {
    prismaMock.ticket.findMany.mockResolvedValue([]);

    await service.findAll();

    expect(prismaMock.ticket.findMany).toHaveBeenCalledWith({
      orderBy: {
        createdAt: 'desc',
      },
    });
  });

  it('lists tickets with status OPEN uses filter', async () => {
    prismaMock.ticket.findMany.mockResolvedValue([]);
    const dto = new FindTicketsDto();
    dto.status = TicketStatus.OPEN;

    await service.findAll(dto);

    expect(prismaMock.ticket.findMany).toHaveBeenCalledWith({
      where: { status: TicketStatus.OPEN },
      orderBy: {
        createdAt: 'desc',
      },
    });
  });

  it('finds a ticket by id when exists', async () => {
    const ticket = {
      id: 5,
      title: 'Ticket',
      description: 'desc',
      status: TicketStatus.OPEN,
    } as unknown as Ticket;
    prismaMock.ticket.findUnique.mockResolvedValue(ticket);

    const result = await service.findOne(5);

    expect(result).toBe(ticket);
    expect(prismaMock.ticket.findUnique).toHaveBeenCalledWith({
      where: { id: 5 },
    });
  });

  it('finds a ticket by id when not exists throws NotFoundException', async () => {
    prismaMock.ticket.findUnique.mockResolvedValue(null);
    await expect(service.findOne(999)).rejects.toBeInstanceOf(
      NotFoundException,
    );
  });

  it('deletes ticket when exists', async () => {
    const ticket = { id: 7, title: 'x' } as unknown as Ticket;
    prismaMock.ticket.findUnique.mockResolvedValue(ticket);
    prismaMock.ticket.delete.mockResolvedValue({});

    await service.delete(7);

    expect(prismaMock.ticket.findUnique).toHaveBeenCalledWith({
      where: { id: 7 },
    });
    expect(prismaMock.ticket.delete).toHaveBeenCalledWith({ where: { id: 7 } });
  });

  it('deletes ticket when not exists throws NotFoundException and does not call delete', async () => {
    prismaMock.ticket.findUnique.mockResolvedValue(null);
    await expect(service.delete(99)).rejects.toBeInstanceOf(NotFoundException);
    expect(prismaMock.ticket.delete).not.toHaveBeenCalled();
  });
});
