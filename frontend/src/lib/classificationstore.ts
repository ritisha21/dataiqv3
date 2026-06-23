// store/classificationStore.ts
// Zustand slice for DB auto-classification state.
// Merge into your existing ETL/connection store or use as a standalone slice.
//
// Usage:
//   import { useClassificationStore } from "@/store/classificationStore";
//   const { dbType, availableModels, classify } = useClassificationStore();

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

// ─── Types ────────────────────────────────────────────────────────────────────

export type DbType = "CRM" | "ERP" | "Hybrid" | "Unknown";

export interface ModelConfig {
  id: string;
  name: string;
  description: string;
  required_signals: string[];
  target_column_hints: string[];
}

export interface ClassificationState {
  // Current connection
  connectionId: string | null;
  connectionString: string | null;
  connectionName: string | null;

  // Classification result
  dbType: DbType;
  confidence: number;
  crmScore: number;
  erpScore: number;
  reasoning: string;

  // Model surface
  availableModels: ModelConfig[];
  selectedModelId: string | null;

  // Schema (for AI chat context)
  availableTables: string[];

  // UI state
  isClassifying: boolean;
  classificationError: string | null;
  lastClassifiedAt: string | null;

  // ── Actions ─────────────────────────────────────────────────────────────────

  /** Call after a schema scan completes. Hits /api/scan/classify. */
  classify: (connectionId: string, connectionString: string) => Promise<void>;

  /** Load models for a known db_type without re-scanning. */
  loadModelsForType: (dbType: DbType) => Promise<void>;

  /** Set the active prediction model. */
  selectModel: (modelId: string) => void;

  /** Store available tables from schema scan (for AI chat grounding). */
  setAvailableTables: (tables: string[]) => void;

  /** Set connection info. */
  setConnection: (id: string, connStr: string, name?: string) => void;

  /** Reset classification state (e.g. when switching connections). */
  resetClassification: () => void;
}

// ─── API helpers ──────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

async function fetchClassification(
  connectionId: string,
  connectionString: string
): Promise<{
  db_type: DbType;
  confidence: number;
  crm_score: number;
  erp_score: number;
  reasoning: string;
  available_models: ModelConfig[];
  matched_crm_tables: string[];
  matched_erp_tables: string[];
}> {
  const res = await fetch(`${API_BASE}/scan/classify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      connection_id: connectionId,
      connection_string: connectionString,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `Classification failed (${res.status})`);
  }
  return res.json();
}

async function fetchModelsForType(dbType: DbType): Promise<ModelConfig[]> {
  const res = await fetch(`${API_BASE}/classify/models/type/${dbType}`);
  if (!res.ok) throw new Error(`Failed to fetch models for type ${dbType}`);
  const data = await res.json();
  return data.models ?? [];
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useClassificationStore = create<ClassificationState>()(
  persist(
    (set, get) => ({
      // Initial state
      connectionId: null,
      connectionString: null,
      connectionName: null,
      dbType: "Unknown",
      confidence: 0,
      crmScore: 0,
      erpScore: 0,
      reasoning: "",
      availableModels: [],
      selectedModelId: null,
      availableTables: [],
      isClassifying: false,
      classificationError: null,
      lastClassifiedAt: null,

      // ── Actions ─────────────────────────────────────────────────────────────

      classify: async (connectionId, connectionString) => {
        set({ isClassifying: true, classificationError: null });
        try {
          const result = await fetchClassification(connectionId, connectionString);

          set({
            dbType: result.db_type,
            confidence: result.confidence,
            crmScore: result.crm_score,
            erpScore: result.erp_score,
            reasoning: result.reasoning,
            availableModels: result.available_models,
            // Auto-select first model if none selected
            selectedModelId:
              get().selectedModelId ?? result.available_models[0]?.id ?? null,
            lastClassifiedAt: new Date().toISOString(),
            isClassifying: false,
          });
        } catch (err) {
          set({
            isClassifying: false,
            classificationError: err instanceof Error ? err.message : String(err),
          });
          throw err;
        }
      },

      loadModelsForType: async (dbType) => {
        try {
          const models = await fetchModelsForType(dbType);
          set({
            dbType,
            availableModels: models,
            selectedModelId: models[0]?.id ?? null,
          });
        } catch (err) {
          console.error("loadModelsForType error:", err);
        }
      },

      selectModel: (modelId) => set({ selectedModelId: modelId }),

      setAvailableTables: (tables) => set({ availableTables: tables }),

      setConnection: (id, connStr, name) =>
        set({
          connectionId: id,
          connectionString: connStr,
          connectionName: name ?? null,
        }),

      resetClassification: () =>
        set({
          dbType: "Unknown",
          confidence: 0,
          crmScore: 0,
          erpScore: 0,
          reasoning: "",
          availableModels: [],
          selectedModelId: null,
          classificationError: null,
          lastClassifiedAt: null,
        }),
    }),
    {
      name: "dataiq-classification",
      storage: createJSONStorage(() => localStorage),
      // Don't persist the connection string to localStorage — security
      partialize: (state) => ({
        connectionId: state.connectionId,
        connectionName: state.connectionName,
        dbType: state.dbType,
        confidence: state.confidence,
        availableModels: state.availableModels,
        selectedModelId: state.selectedModelId,
        availableTables: state.availableTables,
        lastClassifiedAt: state.lastClassifiedAt,
        // Explicitly exclude connectionString
      }),
    }
  )
);


// ─── Hook: auto-classify after scan ──────────────────────────────────────────
//
// Use this in your schema scan component / ETL flow.
// After scan completes, call triggerClassification() and the store
// updates automatically — Models page and AI chat will both pick it up.
//
// Example:
//   const { triggerClassification } = useAutoClassify();
//   // call after successful schema scan:
//   await triggerClassification();

export function useAutoClassify() {
  const { connectionId, connectionString, classify } = useClassificationStore();

  const triggerClassification = async () => {
    if (!connectionId || !connectionString) {
      console.warn("useAutoClassify: no active connection to classify");
      return;
    }
    await classify(connectionId, connectionString);
  };

  return { triggerClassification };
}