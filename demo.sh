#!/usr/bin/env bash
# demo.sh — two-minute scripted demo of hr-project-map.
# Full lifecycle: people -> project -> task -> evidence -> human review
# -> completion -> independent verification, plus the three documented
# refusal cases. Uses a temporary database; never touches ./hrpm.db.
# Run from the repository root. Requires Python 3.8+ and bash.
set -euo pipefail

# Remove temp databases left by previously interrupted demo runs
# (a SIGINT/Ctrl-C kill can bypass the EXIT trap; see verification report).
rm -f /tmp/hrpm-demo-*.db

DB="$(mktemp /tmp/hrpm-demo-XXXXXX.db)"
trap 'rm -f "$DB"' EXIT
echo "demo database: $DB"

python3 -c "from src.db import init_db; init_db('$DB')"

MGR=$(python3 -c "from src import people; print(people.add_person('$DB', 'Jane Doe', 'Manager'))")
WORKER=$(python3 -c "from src import people; print(people.add_person('$DB', 'Sam Lee', 'Employee'))")
echo "people: manager=$MGR worker=$WORKER"

./hrpm --db "$DB" project create --name "Onboarding Revamp" --owner "$MGR" --description "Redesign new-hire onboarding"
PRJ=$(python3 -c "from src import projects; print(projects.list_projects('$DB')[0]['id'])")
./hrpm --db "$DB" task create --project "$PRJ" --title "Draft onboarding checklist" --assignee "$WORKER"
TASK=$(python3 -c "from src import tasks; print(tasks.list_tasks_by_project('$DB', '$PRJ')[0]['id'])")
echo "project=$PRJ task=$TASK"

python3 -c "from src import tasks; tasks.update_task_status('$DB', '$TASK', 'In Progress')"
./hrpm --db "$DB" evidence add --task "$TASK" --by "$WORKER" --type document --ref docs/checklist-v1.md
./hrpm --db "$DB" review start --task "$TASK" --reviewer "$MGR"
./hrpm --db "$DB" review accept --task "$TASK" --reviewer "$MGR" --note "meets spec"
python3 -c "
from src import evidence, completion
evs = evidence.list_evidence_for_task('$DB', '$TASK')
evidence.verify_evidence('$DB', evs[0]['id'], verified_by='$MGR')
completion.complete_task('$DB', '$TASK')
completion.verify_task('$DB', '$TASK', '$MGR')
print('task verified')
"
echo "--- dashboard: verified ---"
./hrpm --db "$DB" dashboard verified

echo "--- refusal cases (all three must fail) ---"
T2=$(python3 -c "from src import tasks; print(tasks.add_task('$DB', '$PRJ', 'Unevidenced task', assignee_id='$WORKER'))")
if python3 -c "from src import completion; completion.complete_task('$DB', '$T2')" 2>/dev/null; then
  echo "UNEXPECTED: unevidenced completion allowed"; exit 1
else
  echo "refused: complete with no evidence"
fi

python3 -c "from src import tasks; tasks.update_task_status('$DB', '$T2', 'In Progress')"
./hrpm --db "$DB" evidence add --task "$T2" --by "$WORKER" --type document --ref docs/draft-v1.md >/dev/null
E2=$(python3 -c "from src import evidence; print(evidence.list_evidence_for_task('$DB', '$T2')[0]['id'])")
if python3 -c "from src import evidence; evidence.verify_evidence('$DB', '$E2', verified_by='$WORKER')" 2>/dev/null; then
  echo "UNEXPECTED: self-verification allowed"; exit 1
else
  echo "refused: verify own evidence"
fi

T3=$(python3 -c "from src import tasks; print(tasks.add_task('$DB', '$PRJ', 'Doomed task', assignee_id='$WORKER'))")
python3 -c "from src import tasks; tasks.update_task_status('$DB', '$T3', 'In Progress')"
./hrpm --db "$DB" evidence add --task "$T3" --by "$WORKER" --type document --ref docs/doomed.md >/dev/null
./hrpm --db "$DB" review start --task "$T3" --reviewer "$MGR" >/dev/null
./hrpm --db "$DB" review reject --task "$T3" --reviewer "$MGR" --reason "not needed" >/dev/null
if python3 -c "from src import tasks; tasks.update_task_status('$DB', '$T3', 'In Progress')" 2>/dev/null; then
  echo "UNEXPECTED: rejected task reopened"; exit 1
else
  echo "refused: reopen rejected task"
fi

echo "demo complete — all lifecycle steps and all three refusals behaved as documented"
