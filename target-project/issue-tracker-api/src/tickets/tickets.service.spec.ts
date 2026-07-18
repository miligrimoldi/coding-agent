import { Test } from '@nestjs/testing';

import { PrismaService } from '../prisma/prisma.service';
import { TicketsService } from './tickets.service';

describe('TicketsService', () => {
    let service: TicketsService;

    const prismaMock = {
        ticket: {
            create: jest.fn(),
            findMany: jest.fn(),
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
});