# Create-only publication of diagnostic-pilot summary exports

The standalone offline pilot summarizer previously wrote `pilot_summary.json`
with `write_text` and `pilot_runs.csv` with mode `w`. Running it again
in the same output workspace could silently replace already-published summary
evidence, despite the pilot runner's fresh-workspace gate and create-only
experimental trace publication. It could also leave a partly written canonical
CSV if the write failed. Re-running summarization is **not** a reason to select
different historical observations.

`scripts/summarize_pilot.py` now fully renders its JSON and CSV first, stages
both in their destination directories, fsyncs the staged bytes and uses
create-only hard links to publish the two canonical paths. An existing regular
file **or symlink** in either position aborts without modifying either output.
A concurrent file created after preflight also cannot be overwritten. If
publication of the second path fails, the first link is removed only when it
still names the inode created by this invocation; competing files are preserved.
Staging files are cleaned after the attempt. The prior CSV column layout and
schema-v5 summary values are unchanged.

This protects local **derived-artifact custody**, not original trace custody.
The two canonical names are published sequentially, not as one atomic
multi-file transaction; readers should still wait for successful completion
and use the independent `validate_pilot_artifacts.py` gate. Filesystem
permissions and postpublication modifications require separate controls.
Some filesystems do not support same-directory hard links; in that case
publication fails closed instead of falling back to replacement writes.
For corrections, preserve the original workspace and explicitly create a
separate new output directory rather than deleting an unfavorable result.

Offline synthetic regression:

```bash
python -m pytest -q tests/test_pilot_summary_create_only_publication.py
python -m pytest -q
```

No treatments or evaluations are executed. The five-task pilot is diagnostic;
frozen ten-task automated findings retain their postcollection chronology and
historical evaluator-policy qualifications; retrospective sensitivity remains
exploratory. Neither the still-unrecovered original 40 report/trace artifacts
nor independent blinded human ratings are authenticated or generated here.
