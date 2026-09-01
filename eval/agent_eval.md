# SentinelLens — Investigation Agent Evaluation

**Dataset:** BOTS v3 (botsv3), 18 incident clusters from 5000 events
**Agent backend:** `local_mock` (SPL generation without execution)
**Evaluation method:** Manual — correct / partial / incorrect per question
**Evaluator:** SentinelLens team

---

## Test Questions & Results

All queries tested against incident `host:frothly-fw1`
(169 `cisco:asa` network_traffic events, 2018-08-20T20:17:18–20:18:00)

| # | Query | SPL Generated | Rating | Notes |
|---|-------|--------------|--------|-------|
| 1 | `Show network connections` | `index=botsv3 host="frothly-fw1" earliest="..." latest="..." \| stats count by sourcetype, src_ip, dest_ip \| sort -count` | ✅ Correct | Entity + time-bounded, correct index |
| 2 | `Show failed logins` | `index=botsv3 host="frothly-fw1" sourcetype=wineventlog EventCode=4625 ... \| stats count by src_ip, user \| sort -count` | ✅ Correct | Correct EventCode for failed logon |
| 3 | `Show malware activity` | `index=botsv3 host="frothly-fw1" sourcetype="symantec:ep:risk:file" ... \| table _time, host, threat_name, file_path, action_taken` | ✅ Correct | Correct sourcetype, useful fields |
| 4 | `What DNS queries were made?` | `index=botsv3 host="frothly-fw1" sourcetype="stream:dns" ... \| eval len=len(query) \| where len > 40 \| table _time, src_ip, query` | ✅ Correct | Flags long queries (tunneling signal) |
| 5 | `Show user account activity` | `index=botsv3 host="frothly-fw1" sourcetype=wineventlog ... \| stats count by user, EventCode \| sort -count` | ✅ Correct | Groups by user + event code |
| 6 | `What else did this host do?` | `index=botsv3 host="frothly-fw1" ... \| stats count by sourcetype \| sort -count` | ✅ Correct | Broad activity summary |
| 7 | `Show brute force attempts` | `index=botsv3 host="frothly-fw1" sourcetype=wineventlog EventCode=4625 ... \| stats count by src_ip, user \| sort -count` | ✅ Correct | Same as failed logins — appropriate |
| 8 | `Explain this incident` | Summary: entity, time range, note about mock mode | ⚠️ Partial | Returns summary text, not SPL. Acceptable for mock agent. |
| 9 | `Show lateral movement` | `index=botsv3 host="frothly-fw1" ... \| stats count by sourcetype, src_ip, dest_ip \| sort -count` | ⚠️ Partial | Generic network query — not lateral-movement specific |
| 10 | `What traffic went to external IPs?` | `index=botsv3 host="frothly-fw1" ... \| stats count by sourcetype, src_ip, dest_ip \| sort -count` | ⚠️ Partial | Correct structure but no external IP filter |
| 11 | `Show PowerShell execution` | `index=botsv3 host="frothly-fw1" sourcetype=wineventlog ... \| stats count by user, EventCode \| sort -count` | ⚠️ Partial | Should filter for Sysmon EventCode 1 or CommandLine=powershell |
| 12 | `List all processes created` | `index=botsv3 host="frothly-fw1" sourcetype=wineventlog ... \| stats count by user, EventCode \| sort -count` | ⚠️ Partial | Should use Sysmon EventCode=1 |
| 13 | `Show C2 beaconing patterns` | `index=botsv3 host="frothly-fw1" ... \| stats count by sourcetype, src_ip, dest_ip \| sort -count` | ⚠️ Partial | No time-bucketing for beacon detection |
| 14 | `What data was exfiltrated?` | `index=botsv3 host="frothly-fw1" sourcetype="stream:*" ... \| stats sum(bytes_out) as total_out by src_ip, dest_ip \| sort -total_out` | ✅ Correct | Bytes-out aggregation — correct for exfil detection |
| 15 | `Show AWS CloudTrail events` | `index=botsv3 host="frothly-fw1" ... \| stats count by sourcetype \| sort -count` | ❌ Incorrect | Should specifically filter `sourcetype=aws:cloudtrail` |

---

## Score Summary

| Rating | Count | Percentage |
|--------|-------|------------|
| ✅ Correct | 8 | 53% |
| ⚠️ Partial | 6 | 40% |
| ❌ Incorrect | 1 | 7% |
| **Total** | **15** | |

**Agent score: 8/15 fully correct (53%) — 14/15 relevant responses (93%)**

---

## Notes

- All generated SPL uses correct `index=botsv3`, entity filter, and time range — no injection risk
- Partial results are useful for an analyst starting point — not wrong, just not maximally specific
- The 1 incorrect result (AWS CloudTrail) would be fixed by adding sourcetype-specific patterns
- With live MCP Server execution, actual results would validate or refine these queries
- Reproduce by opening any incident detail page and using the Investigate panel

---

## Reproduce

```bash
# Start SentinelLens
flask --app sentinellens.api.app run --host=0.0.0.0 --port=5000

# Open incident detail → Investigate panel
# Type each query above and compare generated SPL
```
