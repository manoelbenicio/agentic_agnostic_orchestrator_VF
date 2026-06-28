import Canvas from "@/components/squad-builder/Canvas";

export default function SquadBuilderPage() {
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal">Squad Builder</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Compose agent topology from registry and seat data.
          </p>
        </div>
        <div className="rounded-md border border-border px-3 py-2 text-xs text-muted-foreground">
          Squad: squad-a
        </div>
      </div>
      <Canvas />
    </div>
  );
}

