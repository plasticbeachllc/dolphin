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

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function getZodDef(schema: any): any {
  return schema?._zod?.def ?? schema?._def;
}

function unwrapOptional(inner: ZodTypeAny): { schema: ZodTypeAny; optional: boolean } {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let current: any = inner;
  let optional = false;
  const def = () => getZodDef(current);
  while (def()?.type === "optional" || def()?.type === "default") {
    optional = true;
    current = def().innerType;
  }
  return { schema: current, optional };
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
    // In Zod v4, .int() adds a "number_format" check; detect via checks
    const isInt = def.checks?.some(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (check: any) => (check?._zod?.def?.check ?? check?.check ?? check?.kind) === "number_format"
    );
    return { type: isInt ? "integer" : "number" };
  }

  // z.int() in Zod v4 creates a schema with def.type === "int"
  if (typeName === "int") {
    return { type: "integer" };
  }

  if (typeName === "boolean") {
    return { type: "boolean" };
  }

  if (typeName === "enum") {
    // Zod v4 uses `entries`, v3 uses `values`
    const values = def.entries ?? def.values;
    // entries may be an object { key: value } — extract values
    const enumValues =
      values && typeof values === "object" && !Array.isArray(values) ? Object.values(values) : values;
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
  // Cast to any to prevent TypeScript from evaluating the complex recursive generics
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return zodToJsonSchema(schema as any);
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
