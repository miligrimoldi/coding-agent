import { PrismaService } from '../prisma/prisma.service';
import { CreateTicketDto } from './dto/create-ticket.dto';
export declare class TicketsService {
    private readonly prisma;
    constructor(prisma: PrismaService);
    create(input: CreateTicketDto): import("../generated/prisma/models").Prisma__TicketClient<{
        id: number;
        title: string;
        description: string | null;
        status: import("../generated/prisma/enums").TicketStatus;
        createdAt: Date;
        updatedAt: Date;
    }, never, import("@prisma/client/runtime/client").DefaultArgs, {
        omit: import("../generated/prisma/internal/prismaNamespace").GlobalOmitConfig | undefined;
    }>;
    findAll(): import("../generated/prisma/internal/prismaNamespace").PrismaPromise<{
        id: number;
        title: string;
        description: string | null;
        status: import("../generated/prisma/enums").TicketStatus;
        createdAt: Date;
        updatedAt: Date;
    }[]>;
}
