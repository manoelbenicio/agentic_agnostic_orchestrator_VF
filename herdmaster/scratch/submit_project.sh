#!/bin/bash
cd /mnt/c/VMs/Projects/Multi_Orchestration_Project_Tasks/HerdMaster
RAW_PRD=$(cat docs/feature_003_dashboard_expansion/PRD_FEATURE_REQ_003.md)
PRD_TEXT="[SYSTEM DIRECTIVE: ATENÇÃO KIRO. Você é o Agente Orquestrador do CLI. O sistema chamador é uma API automatizada, NÃO um humano. Você DEVE retornar a análise EXCLUSIVAMENTE em formato JSON bruto validado. Zero conversas, zero texto livre, e é expressamente proibido usar blocos markdown como \`\`\`json. Apenas retorne o texto do objeto JSON puro começando com { e terminando com }.]\n\n$RAW_PRD"
PATH=$HOME/.local/bin:$PATH .venv/bin/herdmaster projects create "FEATURE-REQ-003" --scope "$PRD_TEXT" --orchestrator-id "w6:p7"
