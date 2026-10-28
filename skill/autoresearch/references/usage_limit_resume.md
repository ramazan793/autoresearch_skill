# Usage-limit pauses: checkpoint, then resume by yourself

The harness can cut a turn when the account's usage limit is reached. It
announces it first ("Usage limit reached; a short grace allowance remains").
Subagents do not get that message: they keep running on the same allowance
until they are cut off mid-step, with nothing written down. Without a rule,
every limit pause costs the hours until a human notices and restarts things.
This reference turns a pause into a checkpoint plus an automatic restart.

## 1. When the limit announcement arrives

In this order, within the grace allowance:

1. **Finish the piece in hand** if it is a few steps; otherwise stop it.
2. **Stop every running subagent** with `TaskStop`. A stopped agent keeps its
   transcript and can be resumed later with `SendMessage` (context intact);
   an agent cut off by the harness cannot. Background `nohup` jobs (sweeps,
   trainings) need nothing: they survive the pause.
3. **Write the task `STATE.md`** with a `## Running (paused <time> by the
   usage limit)` block: one line per stopped agent — what it was doing, its
   notes path (and HANDOFF section if it has one), whether it can be resumed
   in place or needs a fresh successor — plus the background jobs still
   running and where their results land. Keep the file under 6000 bytes.
4. **Tell the user** in the final message: limit reached, what is done, what
   is paused, that the hourly resume check will restart it.

Do not spawn new agents after the announcement; they would be cut off too.

## 2. The resume check (set it up at task start)

For any task that will run subagents or background jobs for more than an
hour, create an in-session hourly cron **when the task starts**, not when the
limit hits (the grace allowance may not cover it):

```
CronCreate  cron: "<off-minute> * * * *"   recurring: true
prompt: "Hourly resume check for <repo>. Read <index STATE.md> and the
STATE.md of every task listed as running or paused. If a task was paused by a
usage limit (workers stopped, work unfinished), resume it: restart the stopped
workers from their notes and briefs, then continue the normal flow. If
everything is running or finished, do nothing and reply with one line."
```

Pick a minute that is not :00 or :30. The job is session-only (gone when the
session ends; auto-expires after 7 days): recreate it when a session is
restarted mid-task. If a firing lands while the limit is still active, that
firing is lost and the next one tries again an hour later — that is the
point of a cron over a one-shot wakeup.

## 3. On resume

1. Re-read the task `STATE.md` and the paused agents' notes.
2. **Resume in place** (`SendMessage` to the stopped agent's id with the
   current time, what finished meanwhile, and the remaining items of its
   brief) when its task is unchanged and it stopped before its context
   limit. **Spawn a fresh successor** from the HANDOFF section when the agent
   had reached its context limit or its brief changed (fresh-context rule of
   the subagent playbook).
3. Check what the background jobs produced while paused before restarting
   any of them; drivers that skip finished points can simply be re-run.
4. Update `STATE.md` (`resumed <time>`), then continue.

## 4. At task end

`CronDelete` the resume check together with the other cleanup (§8 of
SKILL.md). A forgotten resume check is harmless but noisy.
