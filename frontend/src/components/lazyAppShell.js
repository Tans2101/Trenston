import { lazyWithReload } from "@/lib/chunkReload";

// Signed-in shell, loaded only after auth resolves so marketing pages skip this code.
export const AppLayout = lazyWithReload(() => import("@/components/AppLayout"));
export const WorkspaceGate = lazyWithReload(() => import("@/pages/WorkspaceGate"));
