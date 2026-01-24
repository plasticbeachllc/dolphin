import type { Tool } from "@modelcontextprotocol/sdk/types.js";
import type { ZodTypeAny } from "zod";
import { z } from "zod";
import { zodToJsonSchema } from "zod-to-json-schema";

type JsonSchema = Tool["inputSchema"] & {
  type?: string | string[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
};

function unwrapOptional(inner: ZodTypeAny): { schema: ZodTypeAny; optional: boolean } {
  let current = inner;
  let optional = false;
  while (current instanceof z.ZodOptional || current instanceof z.ZodDefault) {
    optional = true;
    current = current._def.innerType;
  }
  return { schema: current, optional };
}

function buildFallbackSchema(schema: ZodTypeAny): JsonSchema {
  if (!schema || typeof schema !== "object" || !("_def" in schema)) {
    return { type: "object", properties: {} };
  }
  const typeName = schema._def.typeName as string;

  if (schema instanceof z.ZodString) {
    return { type: "string" };
  }

  if (schema instanceof z.ZodNumber) {
    const isInt = schema._def.checks?.some((check) => check.kind === "int");
    return { type: isInt ? "integer" : "number" };
  }

  if (schema instanceof z.ZodBoolean) {
    return { type: "boolean" };
  }

  if (schema instanceof z.ZodEnum) {
    return { type: "string", enum: schema._def.values };
  }

  if (schema instanceof z.ZodArray) {
    return { type: "array", items: buildFallbackSchema(schema._def.type) };
  }

  if (schema instanceof z.ZodNullable) {
    const innerSchema = buildFallbackSchema(schema._def.innerType);
    const innerType = innerSchema.type ?? "string";
    const types = Array.isArray(innerType) ? innerType : [innerType];
    return { ...innerSchema, type: [...types, "null"] };
  }

  if (schema instanceof z.ZodObject) {
    const shape = typeof schema._def.shape === "function" ? schema._def.shape() : schema._def.shape;
    const properties: Record<string, JsonSchema> = {};
    const required: string[] = [];

    Object.entries(shape).forEach(([key, value]) => {
      if (!value || typeof value !== "object" || !("_def" in value)) {
        return;
      }
      const { schema: inner, optional } = unwrapOptional(value as ZodTypeAny);
      properties[key] = buildFallbackSchema(inner);
      if (!optional) {
        required.push(key);
      }
    });

    const output: JsonSchema = { type: "object", properties };
    if (required.length > 0) {
      output.required = required;
    }
    return output;
  }

  if (typeName === "ZodOptional" || typeName === "ZodDefault") {
    const inner = schema._def.innerType as ZodTypeAny;
    return buildFallbackSchema(inner);
  }

  return { type: "object", properties: {} };
}

export function buildToolInputSchema(schema: ZodTypeAny): Tool["inputSchema"] {
  const jsonSchema = zodToJsonSchema(schema) as JsonSchema & {
    $ref?: string;
    definitions?: Record<string, JsonSchema>;
  };

  if (jsonSchema.type) {
    return jsonSchema;
  }

  if (jsonSchema.$ref && jsonSchema.definitions) {
    const refKey = jsonSchema.$ref.replace("#/definitions/", "");
    const resolved = jsonSchema.definitions[refKey];
    if (resolved?.type) {
      return resolved;
    }
  }

  return buildFallbackSchema(schema);
}
