"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.getPrismaClientClass = getPrismaClientClass;
const runtime = __importStar(require("@prisma/client/runtime/client"));
const config = {
    "previewFeatures": [],
    "clientVersion": "7.8.0",
    "engineVersion": "3c6e192761c0362d496ed980de936e2f3cebcd3a",
    "activeProvider": "sqlite",
    "inlineSchema": "generator client {\n  provider               = \"prisma-client\"\n  output                 = \"../src/generated/prisma\"\n  moduleFormat           = \"cjs\"\n  generatedFileExtension = \"ts\"\n  importFileExtension    = \"ts\"\n}\n\ndatasource db {\n  provider = \"sqlite\"\n}\n\nenum TicketStatus {\n  OPEN\n  IN_PROGRESS\n  RESOLVED\n  CLOSED\n}\n\nmodel Ticket {\n  id          Int          @id @default(autoincrement())\n  title       String\n  description String?\n  status      TicketStatus @default(OPEN)\n  createdAt   DateTime     @default(now())\n  updatedAt   DateTime     @updatedAt\n}\n",
    "runtimeDataModel": {
        "models": {},
        "enums": {},
        "types": {}
    },
    "parameterizationSchema": {
        "strings": [],
        "graph": ""
    }
};
config.runtimeDataModel = JSON.parse("{\"models\":{\"Ticket\":{\"fields\":[{\"name\":\"id\",\"kind\":\"scalar\",\"type\":\"Int\"},{\"name\":\"title\",\"kind\":\"scalar\",\"type\":\"String\"},{\"name\":\"description\",\"kind\":\"scalar\",\"type\":\"String\"},{\"name\":\"status\",\"kind\":\"enum\",\"type\":\"TicketStatus\"},{\"name\":\"createdAt\",\"kind\":\"scalar\",\"type\":\"DateTime\"},{\"name\":\"updatedAt\",\"kind\":\"scalar\",\"type\":\"DateTime\"}],\"dbName\":null}},\"enums\":{},\"types\":{}}");
config.parameterizationSchema = {
    strings: JSON.parse("[\"where\",\"Ticket.findUnique\",\"Ticket.findUniqueOrThrow\",\"orderBy\",\"cursor\",\"Ticket.findFirst\",\"Ticket.findFirstOrThrow\",\"Ticket.findMany\",\"data\",\"Ticket.createOne\",\"Ticket.createMany\",\"Ticket.createManyAndReturn\",\"Ticket.updateOne\",\"Ticket.updateMany\",\"Ticket.updateManyAndReturn\",\"create\",\"update\",\"Ticket.upsertOne\",\"Ticket.deleteOne\",\"Ticket.deleteMany\",\"having\",\"_count\",\"_avg\",\"_sum\",\"_min\",\"_max\",\"Ticket.groupBy\",\"Ticket.aggregate\",\"AND\",\"OR\",\"NOT\",\"id\",\"title\",\"description\",\"TicketStatus\",\"status\",\"createdAt\",\"updatedAt\",\"equals\",\"in\",\"notIn\",\"lt\",\"lte\",\"gt\",\"gte\",\"not\",\"contains\",\"startsWith\",\"endsWith\",\"set\",\"increment\",\"decrement\",\"multiply\",\"divide\"]"),
    graph: "PAsQCRwAACwAMB0AAAQAEB4AACwAMB8CAAAAASABAC4AISEBAC8AISMAADAjIiRAADEAISVAADEAIQEAAAABACABAAAAAQAgCRwAACwAMB0AAAQAEB4AACwAMB8CAC0AISABAC4AISEBAC8AISMAADAjIiRAADEAISVAADEAIQEhAAAyACADAAAABAAgAwAABQAwBAAAAQAgAwAAAAQAIAMAAAUAMAQAAAEAIAMAAAAEACADAAAFADAEAAABACAGHwIAAAABIAEAAAABIQEAAAABIwAAACMCJEAAAAABJUAAAAABAQgAAAkAIAYfAgAAAAEgAQAAAAEhAQAAAAEjAAAAIwIkQAAAAAElQAAAAAEBCAAACwAwAQgAAAsAMAYfAgA8ACEgAQA4ACEhAQA5ACEjAAA6IyIkQAA7ACElQAA7ACECAAAAAQAgCAAADgAgBh8CADwAISABADgAISEBADkAISMAADojIiRAADsAISVAADsAIQIAAAAEACAIAAAQACACAAAABAAgCAAAEAAgAwAAAAEAIA8AAAkAIBAAAA4AIAEAAAABACABAAAABAAgBhUAADMAIBYAADQAIBcAADcAIBgAADYAIBkAADUAICEAADIAIAkcAAAaADAdAAAXABAeAAAaADAfAgAbACEgAQAcACEhAQAdACEjAAAeIyIkQAAfACElQAAfACEDAAAABAAgAwAAFgAwFAAAFwAgAwAAAAQAIAMAAAUAMAQAAAEAIAkcAAAaADAdAAAXABAeAAAaADAfAgAbACEgAQAcACEhAQAdACEjAAAeIyIkQAAfACElQAAfACENFQAAIQAgFgAAKwAgFwAAIQAgGAAAIQAgGQAAIQAgJgIAAAABJwIAAAAEKAIAAAAEKQIAAAABKgIAAAABKwIAAAABLAIAAAABLQIAKgAhDhUAACEAIBgAACkAIBkAACkAICYBAAAAAScBAAAABCgBAAAABCkBAAAAASoBAAAAASsBAAAAASwBAAAAAS0BACgAIS4BAAAAAS8BAAAAATABAAAAAQ4VAAAmACAYAAAnACAZAAAnACAmAQAAAAEnAQAAAAUoAQAAAAUpAQAAAAEqAQAAAAErAQAAAAEsAQAAAAEtAQAlACEuAQAAAAEvAQAAAAEwAQAAAAEHFQAAIQAgGAAAJAAgGQAAJAAgJgAAACMCJwAAACMIKAAAACMILQAAIyMiCxUAACEAIBgAACIAIBkAACIAICZAAAAAASdAAAAABChAAAAABClAAAAAASpAAAAAAStAAAAAASxAAAAAAS1AACAAIQsVAAAhACAYAAAiACAZAAAiACAmQAAAAAEnQAAAAAQoQAAAAAQpQAAAAAEqQAAAAAErQAAAAAEsQAAAAAEtQAAgACEIJgIAAAABJwIAAAAEKAIAAAAEKQIAAAABKgIAAAABKwIAAAABLAIAAAABLQIAIQAhCCZAAAAAASdAAAAABChAAAAABClAAAAAASpAAAAAAStAAAAAASxAAAAAAS1AACIAIQcVAAAhACAYAAAkACAZAAAkACAmAAAAIwInAAAAIwgoAAAAIwgtAAAjIyIEJgAAACMCJwAAACMIKAAAACMILQAAJCMiDhUAACYAIBgAACcAIBkAACcAICYBAAAAAScBAAAABSgBAAAABSkBAAAAASoBAAAAASsBAAAAASwBAAAAAS0BACUAIS4BAAAAAS8BAAAAATABAAAAAQgmAgAAAAEnAgAAAAUoAgAAAAUpAgAAAAEqAgAAAAErAgAAAAEsAgAAAAEtAgAmACELJgEAAAABJwEAAAAFKAEAAAAFKQEAAAABKgEAAAABKwEAAAABLAEAAAABLQEAJwAhLgEAAAABLwEAAAABMAEAAAABDhUAACEAIBgAACkAIBkAACkAICYBAAAAAScBAAAABCgBAAAABCkBAAAAASoBAAAAASsBAAAAASwBAAAAAS0BACgAIS4BAAAAAS8BAAAAATABAAAAAQsmAQAAAAEnAQAAAAQoAQAAAAQpAQAAAAEqAQAAAAErAQAAAAEsAQAAAAEtAQApACEuAQAAAAEvAQAAAAEwAQAAAAENFQAAIQAgFgAAKwAgFwAAIQAgGAAAIQAgGQAAIQAgJgIAAAABJwIAAAAEKAIAAAAEKQIAAAABKgIAAAABKwIAAAABLAIAAAABLQIAKgAhCCYIAAAAAScIAAAABCgIAAAABCkIAAAAASoIAAAAASsIAAAAASwIAAAAAS0IACsAIQkcAAAsADAdAAAEABAeAAAsADAfAgAtACEgAQAuACEhAQAvACEjAAAwIyIkQAAxACElQAAxACEIJgIAAAABJwIAAAAEKAIAAAAEKQIAAAABKgIAAAABKwIAAAABLAIAAAABLQIAIQAhCyYBAAAAAScBAAAABCgBAAAABCkBAAAAASoBAAAAASsBAAAAASwBAAAAAS0BACkAIS4BAAAAAS8BAAAAATABAAAAAQsmAQAAAAEnAQAAAAUoAQAAAAUpAQAAAAEqAQAAAAErAQAAAAEsAQAAAAEtAQAnACEuAQAAAAEvAQAAAAEwAQAAAAEEJgAAACMCJwAAACMIKAAAACMILQAAJCMiCCZAAAAAASdAAAAABChAAAAABClAAAAAASpAAAAAAStAAAAAASxAAAAAAS1AACIAIQAAAAAAAAExAQAAAAEBMQEAAAABATEAAAAjAgExQAAAAAEFMQIAAAABMgIAAAABMwIAAAABNAIAAAABNQIAAAABAAAAAAUVAAYWAAcXAAgYAAkZAAoAAAAAAAUVAAYWAAcXAAgYAAkZAAoBAgECAwEFBgEGBwEHCAEJCgEKDAILDQMMDwENEQIOEgQREwESFAETFQIaGAUbGQs"
};
async function decodeBase64AsWasm(wasmBase64) {
    const { Buffer } = await import('node:buffer');
    const wasmArray = Buffer.from(wasmBase64, 'base64');
    return new WebAssembly.Module(wasmArray);
}
config.compilerWasm = {
    getRuntime: async () => await import("@prisma/client/runtime/query_compiler_fast_bg.sqlite.js"),
    getQueryCompilerWasmModule: async () => {
        const { wasm } = await import("@prisma/client/runtime/query_compiler_fast_bg.sqlite.wasm-base64.js");
        return await decodeBase64AsWasm(wasm);
    },
    importName: "./query_compiler_fast_bg.js"
};
function getPrismaClientClass() {
    return runtime.getPrismaClient(config);
}
//# sourceMappingURL=class.js.map