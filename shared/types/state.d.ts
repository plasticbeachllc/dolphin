import { z } from "zod";
export declare const PlanStepSchema: z.ZodObject<{
    id: z.ZodString;
    order: z.ZodNumber;
    description: z.ZodString;
    action_type: z.ZodEnum<["tool_call", "llm_generation", "user_interaction"]>;
    tool: z.ZodOptional<z.ZodString>;
    status: z.ZodEnum<["pending", "running", "completed", "failed"]>;
    started_at: z.ZodOptional<z.ZodString>;
    completed_at: z.ZodOptional<z.ZodString>;
    input: z.ZodOptional<z.ZodRecord<z.ZodString, z.ZodAny>>;
    output: z.ZodOptional<z.ZodRecord<z.ZodString, z.ZodAny>>;
    error: z.ZodOptional<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    id: string;
    order: number;
    description: string;
    action_type: "tool_call" | "llm_generation" | "user_interaction";
    status: "pending" | "completed" | "failed" | "running";
    error?: string | undefined;
    tool?: string | undefined;
    started_at?: string | undefined;
    completed_at?: string | undefined;
    input?: Record<string, any> | undefined;
    output?: Record<string, any> | undefined;
}, {
    id: string;
    order: number;
    description: string;
    action_type: "tool_call" | "llm_generation" | "user_interaction";
    status: "pending" | "completed" | "failed" | "running";
    error?: string | undefined;
    tool?: string | undefined;
    started_at?: string | undefined;
    completed_at?: string | undefined;
    input?: Record<string, any> | undefined;
    output?: Record<string, any> | undefined;
}>;
export declare const PlanSchema: z.ZodObject<{
    schema_version: z.ZodDefault<z.ZodString>;
    plan: z.ZodObject<{
        id: z.ZodString;
        created_at: z.ZodString;
        updated_at: z.ZodString;
        status: z.ZodEnum<["pending", "executing", "completed", "failed", "blocked"]>;
        mode: z.ZodEnum<["architect", "editor"]>;
        task: z.ZodString;
        workspace_root: z.ZodString;
    }, "strip", z.ZodTypeAny, {
        id: string;
        status: "pending" | "executing" | "completed" | "failed" | "blocked";
        created_at: string;
        updated_at: string;
        mode: "architect" | "editor";
        task: string;
        workspace_root: string;
    }, {
        id: string;
        status: "pending" | "executing" | "completed" | "failed" | "blocked";
        created_at: string;
        updated_at: string;
        mode: "architect" | "editor";
        task: string;
        workspace_root: string;
    }>;
    steps: z.ZodArray<z.ZodObject<{
        id: z.ZodString;
        order: z.ZodNumber;
        description: z.ZodString;
        action_type: z.ZodEnum<["tool_call", "llm_generation", "user_interaction"]>;
        tool: z.ZodOptional<z.ZodString>;
        status: z.ZodEnum<["pending", "running", "completed", "failed"]>;
        started_at: z.ZodOptional<z.ZodString>;
        completed_at: z.ZodOptional<z.ZodString>;
        input: z.ZodOptional<z.ZodRecord<z.ZodString, z.ZodAny>>;
        output: z.ZodOptional<z.ZodRecord<z.ZodString, z.ZodAny>>;
        error: z.ZodOptional<z.ZodString>;
    }, "strip", z.ZodTypeAny, {
        id: string;
        order: number;
        description: string;
        action_type: "tool_call" | "llm_generation" | "user_interaction";
        status: "pending" | "completed" | "failed" | "running";
        error?: string | undefined;
        tool?: string | undefined;
        started_at?: string | undefined;
        completed_at?: string | undefined;
        input?: Record<string, any> | undefined;
        output?: Record<string, any> | undefined;
    }, {
        id: string;
        order: number;
        description: string;
        action_type: "tool_call" | "llm_generation" | "user_interaction";
        status: "pending" | "completed" | "failed" | "running";
        error?: string | undefined;
        tool?: string | undefined;
        started_at?: string | undefined;
        completed_at?: string | undefined;
        input?: Record<string, any> | undefined;
        output?: Record<string, any> | undefined;
    }>, "many">;
}, "strip", z.ZodTypeAny, {
    schema_version: string;
    plan: {
        id: string;
        status: "pending" | "executing" | "completed" | "failed" | "blocked";
        created_at: string;
        updated_at: string;
        mode: "architect" | "editor";
        task: string;
        workspace_root: string;
    };
    steps: {
        id: string;
        order: number;
        description: string;
        action_type: "tool_call" | "llm_generation" | "user_interaction";
        status: "pending" | "completed" | "failed" | "running";
        error?: string | undefined;
        tool?: string | undefined;
        started_at?: string | undefined;
        completed_at?: string | undefined;
        input?: Record<string, any> | undefined;
        output?: Record<string, any> | undefined;
    }[];
}, {
    plan: {
        id: string;
        status: "pending" | "executing" | "completed" | "failed" | "blocked";
        created_at: string;
        updated_at: string;
        mode: "architect" | "editor";
        task: string;
        workspace_root: string;
    };
    steps: {
        id: string;
        order: number;
        description: string;
        action_type: "tool_call" | "llm_generation" | "user_interaction";
        status: "pending" | "completed" | "failed" | "running";
        error?: string | undefined;
        tool?: string | undefined;
        started_at?: string | undefined;
        completed_at?: string | undefined;
        input?: Record<string, any> | undefined;
        output?: Record<string, any> | undefined;
    }[];
    schema_version?: string | undefined;
}>;
export declare const ConversationMessageSchema: z.ZodObject<{
    id: z.ZodString;
    role: z.ZodEnum<["user", "assistant"]>;
    content: z.ZodString;
    timestamp: z.ZodString;
    pinned: z.ZodOptional<z.ZodBoolean>;
}, "strip", z.ZodTypeAny, {
    id: string;
    role: "user" | "assistant";
    content: string;
    timestamp: string;
    pinned?: boolean | undefined;
}, {
    id: string;
    role: "user" | "assistant";
    content: string;
    timestamp: string;
    pinned?: boolean | undefined;
}>;
export declare const ConversationSchema: z.ZodObject<{
    schema_version: z.ZodDefault<z.ZodString>;
    conversation: z.ZodObject<{
        id: z.ZodString;
        created_at: z.ZodString;
        updated_at: z.ZodString;
        workspace_root: z.ZodString;
    }, "strip", z.ZodTypeAny, {
        id: string;
        created_at: string;
        updated_at: string;
        workspace_root: string;
    }, {
        id: string;
        created_at: string;
        updated_at: string;
        workspace_root: string;
    }>;
    messages: z.ZodArray<z.ZodObject<{
        id: z.ZodString;
        role: z.ZodEnum<["user", "assistant"]>;
        content: z.ZodString;
        timestamp: z.ZodString;
        pinned: z.ZodOptional<z.ZodBoolean>;
    }, "strip", z.ZodTypeAny, {
        id: string;
        role: "user" | "assistant";
        content: string;
        timestamp: string;
        pinned?: boolean | undefined;
    }, {
        id: string;
        role: "user" | "assistant";
        content: string;
        timestamp: string;
        pinned?: boolean | undefined;
    }>, "many">;
    summaries: z.ZodOptional<z.ZodArray<z.ZodObject<{
        range_start: z.ZodNumber;
        range_end: z.ZodNumber;
        key_points: z.ZodArray<z.ZodString, "many">;
        created_at: z.ZodString;
    }, "strip", z.ZodTypeAny, {
        created_at: string;
        range_start: number;
        range_end: number;
        key_points: string[];
    }, {
        created_at: string;
        range_start: number;
        range_end: number;
        key_points: string[];
    }>, "many">>;
}, "strip", z.ZodTypeAny, {
    schema_version: string;
    conversation: {
        id: string;
        created_at: string;
        updated_at: string;
        workspace_root: string;
    };
    messages: {
        id: string;
        role: "user" | "assistant";
        content: string;
        timestamp: string;
        pinned?: boolean | undefined;
    }[];
    summaries?: {
        created_at: string;
        range_start: number;
        range_end: number;
        key_points: string[];
    }[] | undefined;
}, {
    conversation: {
        id: string;
        created_at: string;
        updated_at: string;
        workspace_root: string;
    };
    messages: {
        id: string;
        role: "user" | "assistant";
        content: string;
        timestamp: string;
        pinned?: boolean | undefined;
    }[];
    schema_version?: string | undefined;
    summaries?: {
        created_at: string;
        range_start: number;
        range_end: number;
        key_points: string[];
    }[] | undefined;
}>;
export type Plan = z.infer<typeof PlanSchema>;
export type PlanStep = z.infer<typeof PlanStepSchema>;
export type Conversation = z.infer<typeof ConversationSchema>;
export type ConversationMessage = z.infer<typeof ConversationMessageSchema>;
