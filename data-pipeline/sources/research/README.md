# Research batch inputs

`worklist-NN.json` — schools assigned to each batch, most selective first.
`batch-NN.json`    — researched output, merged by `merge_research.py`.

One file per batch so batches never contend for a single file.

## Rules the merge enforces (see tests/test_merge_research.py)

- Every entry needs an `http(s)` `src`. A named professor without a source is
  unverifiable, however plausible, and is dropped.
- "none found", "N/A", "unknown" and friends are dropped rather than stored — a
  school with nothing verifiable gets no section, and absent sections do not
  render.
- Existing sections are never overwritten, so a later weaker pass cannot clobber
  hand-checked data.
