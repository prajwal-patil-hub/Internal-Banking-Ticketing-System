# End-of-Day Settlement Runbook

## 1. Cut-off times

NEFT settles in half-hourly batches until 18:00 on working days. RTGS closes
at 16:30 for customer transactions. IMPS runs 24x7 with no cut-off.

## 2. Reconciliation

### 2.1 Nostro breaks

Any nostro break above Rs 1 lakh is raised as a ticket to Treasury Operations
the same day, with the statement line attached.

### 2.2 Ageing

A break unresolved after 3 working days is escalated to the Treasury head.

## 3. Failure handling

If the settlement file is rejected, re-generate it from the source ledger
rather than editing the rejected file. Edited files break the checksum and are
rejected again.
