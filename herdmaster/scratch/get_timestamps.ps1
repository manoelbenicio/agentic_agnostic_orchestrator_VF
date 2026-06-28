$files = @(
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\.agents\AGENTS.md',
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\checkin_checkout.md',
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\docs\PROMPT_AUDIT_REPORT.md',
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\docs\agent-prompts\README.md',
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\docs\agent-prompts\codex-1-canvas-builder.md',
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\docs\agent-prompts\codex-2-studio.md',
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\docs\agent-prompts\gemini-1-reconciler-voice.md',
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\docs\agent-prompts\gemini-2-dashboard-quality.md',
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\docs\herdmaster-prd\TECH_LEAD_PROMPT.md',
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\docs\herdmaster-prd\AGENT_BRIEFING.md',
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\docs\herdmaster-prd\PRD_HerdMaster_v1.0.md',
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\docs\herdmaster-prd\RESEARCH_Herdr_Capabilities.md',
    'c:\VMs\Projects\Multi_Orchestration_Project_Tasks\docs\herdmaster-prd\ROADMAP_Agile_Sprints.md'
)

foreach ($f in $files) {
    $i = Get-Item $f
    $created  = $i.CreationTimeUtc.ToString('yyyy-MM-ddTHH:mm:ssZ')
    $modified = $i.LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mm:ssZ')
    Write-Output "$($i.Name)|$created|$modified"
}
