import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import type { ZodTypeAny } from "zod";
import { zodToJsonSchema } from "zod-to-json-schema";

/**
 * Internal JSON Schema type for building nested property schemas.
 * This is more permissive than Tool["inputSchema"] which requires type: "object".
 */
interface InternalJsonSchema {
  type?: string | string[];
  properties?: Record<string, InternalJsonSchema>;
  required?: string[];
  items?: InternalJsonSchema;
  enum?: readonly string[];
  [key: string]: unknown;
}

// Zod v4 internal API access — verified against zod@4.3.6.
// v4 stores schema definitions at schema._zod.def; v3 used schema._def.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function getZodDef(schema: any): any {
  return schema?._zod?.def ?? schema?._def;
}

function unwrapOptional(inner: ZodTypeAny): { schema: ZodTypeAny; optional: boolean } {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let current: any = inner;
  let optional = false;
  let d;
  while ((d = getZodDef(current))?.type === "optional" || d?.type === "default") {
    optional = true;
    current = d.innerType;
  }
  return { schema: current, optional };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function isIntegerSchema(def: any): boolean {
  // z.int() — def itself has check: "number_format"
  if (def.check === "number_format") return true;
  // z.number().int() — check is in the checks array.
  // Most fragile introspection point: c._zod.def.check is 4 levels into private API.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (
    def.checks?.some((c: any) => c?._zod?.def?.check === "number_format" || c?.kind === "int") ??
    false
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function buildFallbackSchema(schema: any): InternalJsonSchema {
  const def = getZodDef(schema);
  if (!def) {
    return { type: "object", properties: {} };
  }
  const typeName = def.type as string;

  if (typeName === "string") {
    return { type: "string" };
  }

  if (typeName === "number") {
    return { type: isIntegerSchema(def) ? "integer" : "number" };
  }

  if (typeName === "boolean") {
    return { type: "boolean" };
  }

  if (typeName === "enum") {
    // Zod v4 uses `entries`, v3 uses `values`
    const values = def.entries ?? def.values;
    // entries may be an object { key: value } — extract values
    const enumValues =
      values && typeof values === "object" && !Array.isArray(values)
        ? Object.values(values)
        : values;
    if (!enumValues) return { type: "string" };
    return { type: "string", enum: enumValues };
  }

  if (typeName === "array") {
    // Zod v4 uses `element`, v3 uses `type`
    const elementSchema = def.element ?? def.type;
    return { type: "array", items: elementSchema ? buildFallbackSchema(elementSchema) : {} };
  }

  if (typeName === "nullable") {
    const innerSchema = buildFallbackSchema(def.innerType);
    const innerType = innerSchema.type ?? "string";
    const types = Array.isArray(innerType) ? innerType : [innerType];
    return { ...innerSchema, type: [...types, "null"] };
  }

  if (typeName === "object") {
    const shape = typeof def.shape === "function" ? def.shape() : def.shape;
    const properties: Record<string, InternalJsonSchema> = {};
    const required: string[] = [];

    if (shape && typeof shape === "object") {
      Object.entries(shape).forEach(([key, value]) => {
        if (!value || typeof value !== "object") {
          return;
        }
        const { schema: inner, optional } = unwrapOptional(value as ZodTypeAny);
        properties[key] = buildFallbackSchema(inner);
        if (!optional) {
          required.push(key);
        }
      });
    }

    const output: InternalJsonSchema = { type: "object", properties };
    if (required.length > 0) {
      output.required = required;
    }
    return output;
  }

  if (typeName === "optional" || typeName === "default") {
    return buildFallbackSchema(def.innerType);
  }

  return { type: "object", properties: {} };
}

// Helper to isolate type-heavy zodToJsonSchema call
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function convertZodToJsonSchema(schema: ZodTypeAny): any {
  try {
    // Cast to any to prevent TypeScript from evaluating the complex recursive generics
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return zodToJsonSchema(schema as any);
  } catch (e) {
    console.error("[schema] zodToJsonSchema failed, using fallback:", e);
    return {};
  }
}

type ExtendedJsonSchema = InternalJsonSchema & {
  $ref?: string;
  definitions?: Record<string, InternalJsonSchema>;
};

export function buildToolInputSchema(schema: ZodTypeAny): Tool["inputSchema"] {
  const jsonSchema = convertZodToJsonSchema(schema) as ExtendedJsonSchema;

  if (jsonSchema.type) {
    return jsonSchema as Tool["inputSchema"];
  }

  if (jsonSchema.$ref && jsonSchema.definitions) {
    const refKey = jsonSchema.$ref.replace("#/definitions/", "");
    const resolved = jsonSchema.definitions[refKey];
    if (resolved?.type) {
      return resolved as Tool["inputSchema"];
    }
  }

  return buildFallbackSchema(schema) as Tool["inputSchema"];
}
