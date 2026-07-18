import { Test } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';

import { PrismaService } from '../prisma/prisma.service';
import { TicketsService } from './tickets.service';
import { TicketStatus } from '../generated/prisma/client';

describe('TicketsService', () => {
  let service: TicketsService;

  const prismaMock = {
    ticket: {
      create: jest.fn(),
      findMany: jest.fn(),
      findUnique: jest.fn(),
      delete: jest.fn(),
    },
  } as any;

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

  it('findAll with status OPEN filters by status', async () => {
    prismaMock.ticket.findMany.mockResolvedValue([]);

    await service.findAll({ status: TicketStatus.OPEN });

    expect(prismaMock.ticket.findMany).toHaveBeenCalledWith({
      where: {
        status: TicketStatus.OPEN,
      },
      orderBy: {
        createdAt: 'desc',
      },
    });
  });

  it('findOne returns ticket when exists', async () => {
    const ticket = { id: 1, title: 'Test', description: null, status: 'OPEN' as const };
    prismaMock.ticket.findUnique.mockResolvedValue(ticket);

    const result = await service.findOne(1);

    expect(result).toEqual(ticket);
    expect(prismaMock.ticket.findUnique).toHaveBeenCalledWith({ where: { id: 1 } });
  });

  it('findOne throws NotFoundException when not exists', async () => {
    prismaMock.ticket.findUnique.mockResolvedValue(null);

    await expect(service.findOne(999)).rejects.toBeInstanceOf(NotFoundException);
    expect(prismaMock.ticket.findUnique).toHaveBeenCalledWith({ where: { id: 999 } });
  });

  it('delete existing ticket', async () => {
    prismaMock.ticket.findUnique.mockResolvedValue({ id: 1 });
    prismaMock.ticket.delete.mockResolvedValue({ id: 1 });

    await service.delete(1);

    expect(prismaMock.ticket.delete).toHaveBeenCalledWith({ where: { id: 1 } });
  });

  it('delete not exists throws NotFoundException and does not call delete', async () => {
    prismaMock.ticket.findUnique.mockResolvedValue(null);

    await expect(service.delete(999)).rejects.toBeInstanceOf(NotFoundException);

    expect(prismaMock.ticket.delete).not.toHaveBeenCalled();
  });
});
