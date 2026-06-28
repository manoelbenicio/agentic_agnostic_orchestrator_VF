import sys, json

data = json.load(sys.stdin)
print(f"Total: {len(data)} tasks\n")
for t in data:
    print(f"ID:          {t.get('id')}")
    print(f"Title:       {t.get('title')}")
    print(f"State:       {t.get('state')}")
    print(f"Assigned:    {t.get('assigned_to', '-')}")
    print(f"Project:     {t.get('project_id', '-')}")
    print(f"Updated:     {t.get('updated_at', '-')}")
    reason = t.get('failure_reason') or t.get('error') or '-'
    print(f"Fail reason: {reason}")
    print("---")
